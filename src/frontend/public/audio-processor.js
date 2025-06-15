/**
 * オーディオデータを処理し、メインスレッドに送信するAudioWorkletProcessor。
 *
 * このプロセッサは、入力されたオーディオデータを16-bit PCM形式に変換し、
 * オプションでダウンサンプリングを行ってから、メインスreadに転送します。
 *
 * @class AudioProcessor
 * @extends AudioWorkletProcessor
 */
class AudioProcessor extends AudioWorkletProcessor {
  /**
   * @constructor
   */
  constructor() {
    super();
    this.port.onmessage = (event) => {
      // メインスレッドからのメッセージは今のところ使わない
    };
  }

  /**
   * オーディオデータを処理するメインの関数。
   * 入力バッファを受け取り、処理してport経由で送信します。
   *
   * @param {Float32Array[][]} inputs - 入力オーディオチャンネルの配列
   * @param {Float32Array[][]} outputs - 出力オーディオチャンネルの配列
   * @param {Record<string, Float32Array>} parameters - オーディオパラメータ
   * @returns {boolean} - プロセッサをアクティブに保つ場合はtrue
   */
  process(inputs, outputs, parameters) {
    // 複数の入力を考慮するが、通常は1つだけ
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true; // 音声入力がない場合は何もしない
    }

    // このプロセッサはモノラル音声を想定
    const channelData = input[0];

    // Float32 (-1.0 to 1.0) から Int16 (-32768 to 32767) へ変換
    const pcmData = new Int16Array(channelData.length);
    for (let i = 0; i < channelData.length; i++) {
      let s = Math.max(-1, Math.min(1, channelData[i]));
      pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // 変換したPCMデータをメインスレッドに送信
    // transferの対象として、pcmData.bufferを渡すことで、コピーではなく所有権を移譲し、パフォーマンスを向上させる
    this.port.postMessage(pcmData.buffer, [pcmData.buffer]);

    // プロセッサをアクティブに保つ
    return true;
  }
}

// プロセッサを登録
registerProcessor('audio-processor', AudioProcessor); 