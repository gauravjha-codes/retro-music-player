import sys
import os
import random
import logging
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSlider, 
                             QFileDialog, QListWidget, QMessageBox, QProgressBar)
from PyQt5.QtGui import QFont, QIcon, QPalette, QColor, QPixmap, QDragEnterEvent, QDropEvent
from PyQt5.QtCore import Qt, QTimer, QUrl, pyqtSignal
import pygame
from pygame import mixer
import sounddevice as sd
import soundfile as sf
import numpy as np
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import APIC
import json

# Set up logging
logging.basicConfig(filename='player_errors.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class RetroMusicPlayer(QMainWindow):
    SUPPORTED_FORMATS = ['.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma', '.m4a', '.aiff', '.opus']
    update_progress_signal = pyqtSignal(float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Retro Music Player")
        self.setGeometry(100, 100, 800, 750)
        self.setWindowIcon(QIcon("retro_icon.png"))
        self.setAcceptDrops(True)
        self.setup_style("80s_neon")  # Default theme
        
        self.playlist = []
        self.current_track_index = 0
        self.is_playing = False
        self.is_shuffled = False
        self.is_repeated = False
        self.crossfade_duration = 2.0  # Seconds
        
        pygame.mixer.init()
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.equalizer_timer = QTimer(self)
        self.equalizer_timer.timeout.connect(self.update_equalizer)
        self.visualizer_timer = QTimer(self)
        self.visualizer_timer.timeout.connect(self.update_visualizer)
        
        self.init_ui()
        self.setup_shortcuts()
        
    def setup_style(self, theme):
        themes = {
            "80s_neon": {
                "bg_color": "#1A1A2E", "text_color": "#00FFCC", "btn_bg": "#2E2E4A",
                "btn_border": "#00FFCC", "hover_bg": "#00FFCC", "hover_text": "#2E2E4A"
            },
            "90s_crt": {
                "bg_color": "#2A2A3A", "text_color": "#FFD700", "btn_bg": "#4A2C2A",
                "btn_border": "#FFD700", "hover_bg": "#FFD700", "hover_text": "#4A2C2A"
            }
        }
        theme_colors = themes.get(theme, themes["80s_neon"])
        
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme_colors['bg_color']};
                color: {theme_colors['text_color']};
                border: 3px solid {theme_colors['btn_border']};
            }}
            QPushButton {{
                background-color: {theme_colors['btn_bg']};
                color: {theme_colors['text_color']};
                border: 3px solid {theme_colors['btn_border']};
                padding: 12px;
                font-family: 'VT323', monospace;
                font-size: 16px;
                text-transform: uppercase;
            }}
            QPushButton:hover {{
                background-color: {theme_colors['hover_bg']};
                color: {theme_colors['hover_text']};
            }}
            QLabel {{
                color: {theme_colors['text_color']};
                font-family: 'VT323', monospace;
                font-size: 18px;
            }}
            QSlider::handle:horizontal {{
                background: {theme_colors['text_color']};
                width: 20px;
                margin: -6px 0;
                border-radius: 10px;
                border: 2px solid {theme_colors['btn_bg']};
            }}
            QSlider::groove:horizontal {{
                background: {theme_colors['btn_bg']};
                height: 12px;
                border: 2px solid {theme_colors['btn_border']};
            }}
            QProgressBar {{
                background-color: {theme_colors['btn_bg']};
                border: 2px solid {theme_colors['btn_border']};
                height: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {theme_colors['text_color']};
            }}
            QListWidget {{
                background-color: {theme_colors['bg_color']};
                color: {theme_colors['text_color']};
                border: 2px solid {theme_colors['btn_border']};
                font-family: 'VT323', monospace;
                font-size: 16px;
            }}
        """)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Theme Switch
        theme_layout = QHBoxLayout()
        self.theme_80s_btn = QPushButton("80s Neon")
        self.theme_90s_btn = QPushButton("90s CRT")
        self.theme_80s_btn.clicked.connect(lambda: self.change_theme("80s_neon"))
        self.theme_90s_btn.clicked.connect(lambda: self.change_theme("90s_crt"))
        theme_layout.addWidget(self.theme_80s_btn)
        theme_layout.addWidget(self.theme_90s_btn)
        main_layout.addLayout(theme_layout)
        
        # Visualizer
        self.visualizer_label = QLabel()
        self.visualizer_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.visualizer_label)
        
        # Album Art
        self.art_label = QLabel()
        self.art_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.art_label)
        
        # Track Display
        self.track_label = QLabel("No Track Selected")
        self.track_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.track_label)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.mousePressEvent = self.seek_to_position
        main_layout.addWidget(self.progress_bar)
        
        # Equalizer Display and Controls
        eq_layout = QHBoxLayout()
        self.equalizer_label = QLabel("Equalizer: [   ]")
        self.equalizer_label.setAlignment(Qt.AlignCenter)
        self.bass_slider = QSlider(Qt.Horizontal)
        self.mid_slider = QSlider(Qt.Horizontal)
        self.treble_slider = QSlider(Qt.Horizontal)
        for slider in [self.bass_slider, self.mid_slider, self.treble_slider]:
            slider.setRange(-12, 12)
            slider.setValue(0)
            slider.valueChanged.connect(self.adjust_equalizer)
        eq_layout.addWidget(QLabel("Bass"))
        eq_layout.addWidget(self.bass_slider)
        eq_layout.addWidget(QLabel("Mid"))
        eq_layout.addWidget(self.mid_slider)
        eq_layout.addWidget(QLabel("Treble"))
        eq_layout.addWidget(self.treble_slider)
        main_layout.addLayout(eq_layout)
        
        # Playlist
        self.playlist_widget = QListWidget()
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected_track)
        main_layout.addWidget(self.playlist_widget)
        
        # Volume Control
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.valueChanged.connect(self.adjust_volume)
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        main_layout.addLayout(volume_layout)
        
        # Controls Layout
        controls_layout = QHBoxLayout()
        self.prev_btn = QPushButton("⏮ Prev")
        self.play_btn = QPushButton("▶ Play")
        self.next_btn = QPushButton("⏭ Next")
        self.shuffle_btn = QPushButton("🔀 Shuffle")
        self.repeat_btn = QPushButton("🔁 Repeat")
        self.add_btn = QPushButton("➕ Add Tracks")
        self.save_btn = QPushButton("💾 Save")
        self.load_btn = QPushButton("📂 Load")
        
        self.prev_btn.clicked.connect(self.prev_track)
        self.play_btn.clicked.connect(self.toggle_play)
        self.next_btn.clicked.connect(self.next_track)
        self.shuffle_btn.clicked.connect(self.toggle_shuffle)
        self.repeat_btn.clicked.connect(self.toggle_repeat)
        self.add_btn.clicked.connect(self.add_tracks)
        self.save_btn.clicked.connect(self.save_playlist)
        self.load_btn.clicked.connect(self.load_playlist)
        
        controls_layout.addWidget(self.prev_btn)
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.next_btn)
        controls_layout.addWidget(self.shuffle_btn)
        controls_layout.addWidget(self.repeat_btn)
        controls_layout.addWidget(self.add_btn)
        controls_layout.addWidget(self.save_btn)
        controls_layout.addWidget(self.load_btn)
        main_layout.addLayout(controls_layout)
        
    def setup_shortcuts(self):
        pass
        
    def change_theme(self, theme):
        self.setup_style(theme)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            
    def dropEvent(self, event: QDropEvent):
        urls = [u.toLocalFile() for u in event.mimeData().urls()]
        for url in urls:
            file_ext = os.path.splitext(url)[1].lower()
            if file_ext in self.SUPPORTED_FORMATS:
                try:
                    self.playlist.append(url)
                    track_name = self.get_track_metadata(url)
                    total_length = MP3(url).info.length if file_ext == '.mp3' else 0
                    self.playlist_widget.addItem(f"{track_name} ({int(total_length)}s)")
                    self.update_album_art(url)
                except Exception as e:
                    logging.error(f"Drop error for {url}: {str(e)}")
                    QMessageBox.warning(self, "File Error", f"Could not load {os.path.basename(url)}: {str(e)}")
            else:
                QMessageBox.warning(self, "Unsupported Format", f"The file {os.path.basename(url)} is not supported.")
        
    def adjust_volume(self, value):
        pygame.mixer.music.set_volume(value / 100.0)
        
    def update_progress(self):
        if pygame.mixer.music.get_busy():
            current_pos = pygame.mixer.music.get_pos() / 1000
            try:
                if self.playlist and self.current_track_index < len(self.playlist):
                    total_length = MP3(self.playlist[self.current_track_index]).info.length
                    progress = int((current_pos / total_length) * 100) if total_length > 0 else 0
                    self.progress_bar.setValue(progress)
                    self.track_label.setText(f"{self.get_track_metadata(self.playlist[self.current_track_index])} ({int(current_pos)}/{int(total_length)}s)")
            except Exception as e:
                logging.error(f"Progress update error: {str(e)}")
                pass
        
    def seek_to_position(self, event):
        if self.playlist and self.current_track_index < len(self.playlist):
            total_length = MP3(self.playlist[self.current_track_index]).info.length
            click_pos = event.pos().x() / self.progress_bar.width()
            new_pos = click_pos * total_length
            pygame.mixer.music.set_pos(new_pos)
            self.update_progress()
        
    def update_equalizer(self):
        bars = ["█" if random.random() > 0.3 else " " for _ in range(5)]
        self.equalizer_label.setText(f"Equalizer: [{''.join(bars)}]")
        
    def adjust_equalizer(self):
        # Placeholder for actual equalizer adjustment
        bass = self.bass_slider.value() / 12.0
        mid = self.mid_slider.value() / 12.0
        treble = self.treble_slider.value() / 12.0
        print(f"Equalizer: Bass={bass}, Mid={mid}, Treble={treble}")
        
    def add_tracks(self):
        supported_formats_str = " ".join([f"*{fmt}" for fmt in self.SUPPORTED_FORMATS])
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add Music Files", "", f"Audio Files ({supported_formats_str})"
        )
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in self.SUPPORTED_FORMATS:
                try:
                    self.playlist.append(file)
                    track_name = self.get_track_metadata(file)
                    total_length = MP3(file).info.length if file_ext == '.mp3' else 0
                    self.playlist_widget.addItem(f"{track_name} ({int(total_length)}s)")
                    self.update_album_art(file)
                except Exception as e:
                    logging.error(f"Add track error for {file}: {str(e)}")
                    QMessageBox.warning(self, "File Error", f"Could not load {os.path.basename(file)}: {str(e)}")
            else:
                QMessageBox.warning(self, "Unsupported Format", f"The file {os.path.basename(file)} is not supported.")
        
    def get_track_metadata(self, file):
        try:
            ext = os.path.splitext(file)[1].lower()
            if ext == '.mp3':
                audio = EasyID3(file)
                return audio.get('title', [os.path.basename(file)])[0]
            elif ext == '.flac':
                audio = FLAC(file)
                return audio.get('title', [os.path.basename(file)])[0]
            elif ext == '.ogg':
                audio = OggVorbis(file)
                return audio.get('title', [os.path.basename(file)])[0]
            return os.path.basename(file)
        except Exception as e:
            logging.error(f"Metadata error for {file}: {str(e)}")
            return os.path.basename(file)
        
    def update_album_art(self, file):
        try:
            if file.lower().endswith('.mp3'):
                audio = MP3(file)
                if audio.tags and 'APIC:' in audio.tags:
                    apic = audio.tags.getall('APIC:')[0]
                    pixmap = QPixmap()
                    pixmap.loadFromData(apic.data)
                    self.art_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    self.art_label.clear()
            else:
                self.art_label.clear()
        except Exception as e:
            logging.error(f"Album art error for {file}: {str(e)}")
            self.art_label.clear()
        
    def play_selected_track(self, item):
        self.current_track_index = self.playlist_widget.row(item)
        self.play_track()
        
    def play_track(self):
        if self.playlist:
            track = self.playlist[self.current_track_index]
            try:
                if self.is_playing:
                    mixer.music.fadeout(int(self.crossfade_duration * 1000))
                mixer.music.load(track)
                mixer.music.play()
                track_name = self.get_track_metadata(track)
                self.update_album_art(track)
                self.play_btn.setText("⏸ Pause")
                self.is_playing = True
                self.progress_timer.start(1000)
                self.equalizer_timer.start(100)
                self.visualizer_timer.start(50)  # Start visualizer when playing
            except Exception as e:
                logging.error(f"Playback error for {track}: {str(e)}")
                QMessageBox.critical(self, "Playback Error", f"Could not play {os.path.basename(track)}: {str(e)}")
        
    def toggle_play(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.play_btn.setText("▶ Play")
            self.is_playing = False
            self.progress_timer.stop()
            self.equalizer_timer.stop()
            self.visualizer_timer.stop()
        else:
            pygame.mixer.music.unpause()
            self.play_btn.setText("⏸ Pause")
            self.is_playing = True
            self.progress_timer.start(1000)
            self.equalizer_timer.start(100)
            self.visualizer_timer.start(50)
        
    def next_track(self):
        if self.playlist:
            if self.is_shuffled:
                self.current_track_index = random.randint(0, len(self.playlist) - 1)
            else:
                self.current_track_index = (self.current_track_index + 1) % len(self.playlist)
            if not self.is_repeated and self.current_track_index == 0 and pygame.mixer.music.get_pos() == -1:
                self.toggle_play()
            else:
                self.play_track()
        
    def prev_track(self):
        if self.playlist:
            if self.is_shuffled:
                self.current_track_index = random.randint(0, len(self.playlist) - 1)
            else:
                self.current_track_index = (self.current_track_index - 1) % len(self.playlist)
            self.play_track()
        
    def toggle_shuffle(self):
        self.is_shuffled = not self.is_shuffled
        self.shuffle_btn.setText("🔀 Shuffle" if not self.is_shuffled else "🔀 Unshuffle")
        
    def toggle_repeat(self):
        self.is_repeated = not self.is_repeated
        self.repeat_btn.setText("🔁 Repeat" if not self.is_repeated else "🔁 No Repeat")
        
    def save_playlist(self):
        if self.playlist:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "JSON Files (*.json)")
            if file_path:
                with open(file_path, 'w') as f:
                    json.dump(self.playlist, f)
                QMessageBox.information(self, "Success", "Playlist saved successfully.")
        else:
            QMessageBox.warning(self, "No Playlist", "No tracks to save.")
            
    def load_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Playlist", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    self.playlist = json.load(f)
                self.playlist_widget.clear()
                for track in self.playlist:
                    track_name = self.get_track_metadata(track)
                    total_length = MP3(track).info.length if track.lower().endswith('.mp3') else 0
                    self.playlist_widget.addItem(f"{track_name} ({int(total_length)}s)")
                QMessageBox.information(self, "Success", "Playlist loaded successfully.")
            except Exception as e:
                logging.error(f"Load playlist error: {str(e)}")
                QMessageBox.critical(self, "Load Error", f"Could not load playlist: {str(e)}")

    def update_visualizer(self):
        if self.is_playing:
            # Simulate amplitude with random values (placeholder)
            bars = [max(1, int(random.uniform(1, 10))) for _ in range(8)]
            visualizer_text = " ".join([f"█" * bar for bar in bars])
            self.visualizer_label.setText(f"Visualizer: {visualizer_text}")
        else:
            self.visualizer_label.setText("Visualizer: [   ]")

def main():
    app = QApplication(sys.argv)
    player = RetroMusicPlayer()
    player.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()