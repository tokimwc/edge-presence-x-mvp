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
   * @returns {boolean} - プロセッサをアクティブに保つ場合はtrue
   */
  process(inputs) {
    // We only use the first input, which is the microphone.
    // The input contains an array of channels. We only use the first channel.
    const inputChannel = inputs[0][0];

    // If there is audio data, post it back to the main thread.
    // We transfer the underlying ArrayBuffer to avoid copying, which is more efficient.
    if (inputChannel) {
      this.port.postMessage(inputChannel.buffer, [inputChannel.buffer]);
    }

    // Return true to keep the processor alive.
    return true;
  }
}

// Register the processor, so it can be used in the main thread.
registerProcessor('audio-processor', AudioProcessor); 