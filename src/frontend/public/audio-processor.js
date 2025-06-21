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

    // inputChannelはFloat32Array
    // もしデータがあれば、メインスレッドにそのバッファを送信する
    // コピーを避けるために、ArrayBufferを直接転送 (transferable) するのが効率的
    if (inputChannel instanceof Float32Array) {
      this.port.postMessage(inputChannel.buffer, [inputChannel.buffer]);
    }

    // プロセッサをアクティブに保つためにtrueを返す
    return true;
  }
}

// Register the processor, so it can be used in the main thread.
registerProcessor('audio-processor', AudioProcessor); 