# このモジュールは NumPy ライブラリに依存しています。
# プロジェクトの requirements.txt に 'numpy' が含まれていることを確認してください。
# 例: numpy>=1.20.0

import logging
import numpy as np

# モジュールレベルのロギング設定
# アプリケーション全体でbasicConfigが設定されることを推奨しますが、
# speech_processor.pyのスタイル及び単体テストの便宜を考慮してここに記述します。
logging.basicConfig(
    level=logging.INFO,  # 通常時はINFO、デバッグ時はDEBUGに変更してね
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class PitchWorker:
    """
    音声チャンクからリアルタイムでピッチ（基本周波数）を推定するクラス。
    自己相関アルゴリズムを使用します。
    """
    def __init__(self, sample_rate: int, channels: int, sample_width: int, 
                 min_freq: float = 50.0, max_freq: float = 600.0, 
                 confidence_threshold: float = 0.1):
        """
        PitchWorkerを初期化します。

        Args:
            sample_rate (int): 音声データのサンプリングレート (Hz)。
            channels (int): チャンネル数 (現在はモノラルのみ対応)。
            sample_width (int): 1サンプルあたりのバイト数 (例: 2 for 16-bit PCM)。
            min_freq (float): 推定する最小周波数 (Hz)。
            max_freq (float): 推定する最大周波数 (Hz)。
            confidence_threshold (float): ピッチ推定の信頼度閾値 (正規化された自己相関ピーク値)。
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width
        self.min_freq = min_freq
        self.max_freq = max_freq
        self.confidence_threshold = confidence_threshold

        if self.channels != 1:
            self.logger.warning(
                f"チャンネル数が {self.channels} ですが、ピッチ解析は最初のチャンネルのデータのみを使用します。"
            )

        if self.sample_width == 2: # 16-bit PCM (例: pyaudio.paInt16)
            self.dtype = np.int16
        elif self.sample_width == 1: # 8-bit PCM (例: pyaudio.paInt8)
            self.dtype = np.int8 
            self.logger.warning("8-bit (sample_width=1) PCM を使用します。データが符号付き整数 (np.int8) であることを確認してください。")
        else:
            msg = (f"サポートされていないサンプル幅: {self.sample_width} バイト。 "
                   f"現在は 1 または 2 バイトのPCM整数型のみサポートしています。")
            self.logger.error(msg)
            raise ValueError(msg)

        # 自己相関を計算するためのラグの範囲 (サンプル数単位)
        # sample_rate / freq = period_in_samples (ラグ)
        self.min_lag = int(self.sample_rate / self.max_freq)
        if self.min_lag == 0: # max_freq が高すぎる場合、ラグが0になるのを防ぐ
            self.min_lag = 1 
        self.max_lag = int(self.sample_rate / self.min_freq)
        
        self.logger.info(
            f"🎶 PitchWorker 初期化完了！ Rate: {self.sample_rate}Hz, Channels: {self.channels}, "
            f"Width: {self.sample_width}bytes (dtype: {self.dtype}), "
            f"周波数範囲: [{self.min_freq:.1f}-{self.max_freq:.1f}]Hz, "
            f"ラグ範囲: [{self.min_lag}-{self.max_lag}] サンプル, "
            f"信頼度閾値: {self.confidence_threshold}"
        )

    def _bytes_to_numpy_array(self, audio_chunk: bytes) -> np.ndarray | None:
        """
        bytes形式の音声チャンクをNumPy配列に変換します。
        処理できない場合はNoneを返します。
        """
        if not audio_chunk:
            self.logger.debug("空のオーディオチャンクを受け取りました。")
            return None
        try:
            samples = np.frombuffer(audio_chunk, dtype=self.dtype)
        except ValueError as e:
            self.logger.error(f"NumPy配列への変換に失敗: {e}。チャンク長: {len(audio_chunk)}, dtype: {self.dtype}")
            return None

        if self.channels > 1:
            # マルチチャンネルの場合、最初のチャンネルのデータを使用 (今後の改善点)
            try:
                samples = samples[::self.channels]
            except IndexError:
                self.logger.warning(f"マルチチャンネルデータの処理中にIndexError。データが不完全か、チャンネル数とデータ長が不整合の可能性があります。サンプル長: {len(samples)}")
                return None
        
        return samples

    def _autocorrelate_fft(self, signal: np.ndarray) -> np.ndarray | None:
        """
        信号の自己相関をFFTを使用して効率的に計算します。
        結果は正のラグ部分のみで、ラグ0で正規化されます。
        """
        if signal is None or len(signal) == 0:
            self.logger.debug("自己相関計算のための信号が空です。")
            return None
            
        n = len(signal)
        # FFTの効率を上げるため、長さをゼロパディング (2のべき乗長が理想的だが、ここでは2n-1以上)
        fft_len = 1
        while fft_len < 2 * n - 1: 
            fft_len <<= 1
        
        try:
            # 実数FFT
            fft_signal = np.fft.rfft(signal, n=fft_len)
            # パワースペクトル密度
            power_spectrum = fft_signal * np.conj(fft_signal)
            # 逆FFTで自己相関関数へ
            autocorr = np.fft.irfft(power_spectrum, n=fft_len)
        except Exception as e:
            self.logger.error(f"FFTまたはIFFTの計算中にエラー: {e}")
            return None
        
        # 正のラグ部分を取り出し、ラグ0で正規化
        autocorr_positive_lag = autocorr[:n] 
        if autocorr_positive_lag[0] == 0: # 無音の場合など、ラグ0が0になるのを防ぐ
            self.logger.debug("自己相関のラグ0の値が0です。無音の可能性があります。")
            # 全て0の配列を返すと、後の処理でエラーになる可能性があるためNoneを返す
            return None 
        
        return autocorr_positive_lag / autocorr_positive_lag[0]

    def analyze_pitch(self, audio_chunk: bytes) -> float | None:
        """
        与えられた音声チャンクの基本周波数を推定します。

        Args:
            audio_chunk (bytes): 解析対象の音声データチャンク。

        Returns:
            float | None: 推定された基本周波数 (Hz)。検出できない場合はNone。
        """
        samples = self._bytes_to_numpy_array(audio_chunk)

        # サンプル数がmax_lag（検出したい最も低い周波数の周期）より短いと、そのピッチは検出できない
        if samples is None or len(samples) < self.max_lag:
            actual_len = len(samples) if samples is not None else 0
            self.logger.debug(
                f"サンプル数がピッチ検出に不十分 (現: {actual_len}, 要: >{self.max_lag}) または変換失敗。ピッチ解析スキップ。"
            )
            return None

        autocorr = self._autocorrelate_fft(samples)

        if autocorr is None or len(autocorr) <= self.min_lag:
            self.logger.debug(f"自己相関の計算結果が不十分またはエラー。autocorr長: {len(autocorr) if autocorr is not None else 'None'}, min_lag: {self.min_lag}")
            return None

        # ピーク探索範囲を決定 (min_lag から max_lag の間)
        # autocorr配列のインデックスはラグ値に対応
        search_end_lag_idx = min(self.max_lag, len(autocorr) - 1)

        if self.min_lag > search_end_lag_idx:
            self.logger.debug(
                f"有効なピーク探索ラグ範囲がありません。min_lag: {self.min_lag}, search_end_lag_idx: {search_end_lag_idx}"
            )
            return None

        search_range_autocorr = autocorr[self.min_lag : search_end_lag_idx + 1]
        
        if len(search_range_autocorr) == 0:
            self.logger.debug("自己相関のピーク探索範囲が空です。")
            return None
        
        try:
            # 探索範囲内での相対的なピークインデックス
            relative_peak_index = np.argmax(search_range_autocorr)
            # 自己相関配列全体での絶対的なラグ値 (インデックス)
            peak_lag_idx = self.min_lag + relative_peak_index
        except ValueError: # search_range_autocorrが空の場合など
            self.logger.debug("自己相関の探索範囲で argmax エラー。")
            return None
        
        # ピークのラグ値 (サンプル数) が0の場合は無効
        if peak_lag_idx == 0: 
            self.logger.debug("ピークのラグが0と検出されました。有効なピッチではありません。")
            return None
            
        estimated_frequency = self.sample_rate / peak_lag_idx
        
        # ピークの信頼性を確認 (正規化された自己相関値が閾値以上か)
        peak_value = autocorr[peak_lag_idx]
        if peak_value < self.confidence_threshold:
            self.logger.debug(
                f"推定ピッチの信頼度が低すぎます (ピーク値: {peak_value:.3f} < 閾値: {self.confidence_threshold}). "
                f"周波数: {estimated_frequency:.2f} Hz は破棄します。"
            )
            return None

        self.logger.debug(
            f"🎤 推定ピッチ: {estimated_frequency:.2f} Hz (ラグ: {peak_lag_idx} samples, ピーク値: {peak_value:.3f})"
        )
        return float(estimated_frequency)

# --- (オプション) テスト用の簡単なコード ---
# if __name__ == '__main__':
#     # このテストを実行する場合、loggingレベルをDEBUGにすると詳細が見れます
#     # logging.getLogger("PitchWorker").setLevel(logging.DEBUG)
#     
#     # ダミーの音声データを作成 (例: 440Hzのサイン波)
#     SAMPLE_RATE = 16000
#     DURATION = 0.1 # 100ms
#     FREQUENCY = 440  # A4 note
#     N_CHANNELS = 1
#     SAMPLE_WIDTH = 2 # 16-bit
# 
#     t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), endpoint=False)
#     audio_signal = (np.sin(2 * np.pi * FREQUENCY * t) * (2**15 - 1)).astype(np.int16) # 16-bit
#     audio_bytes = audio_signal.tobytes()
# 
#     # PitchWorkerのインスタンス化
#     pitch_worker = PitchWorker(sample_rate=SAMPLE_RATE, channels=N_CHANNELS, sample_width=SAMPLE_WIDTH)
#     
#     print(f"テスト用音声: {FREQUENCY}Hz のサイン波 ({DURATION*1000:.0f}ms)")
#     estimated_pitch = pitch_worker.analyze_pitch(audio_bytes)
# 
#     if estimated_pitch is not None:
#         print(f"推定されたピッチ: {estimated_pitch:.2f} Hz")
#     else:
#         print("ピッチは検出できませんでした。")
# 
#     # 無音テスト
#     silent_audio_bytes = (np.zeros(int(SAMPLE_RATE * DURATION))).astype(np.int16).tobytes()
#     print("\\n無音データのテスト:")
#     estimated_pitch_silent = pitch_worker.analyze_pitch(silent_audio_bytes)
#     if estimated_pitch_silent is not None:
#         print(f"推定されたピッチ (無音): {estimated_pitch_silent:.2f} Hz")
#     else:
#         print("ピッチは検出できませんでした (無音)。(期待通り)") 