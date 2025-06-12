import { VRM, VRMExpressionPresetName } from '@pixiv/three-vrm'
import { mapVolumeToJaw } from './utils/mapVolumeToJaw'

/**
 * Simple microphone based lip sync controller.
 */
export class LipSync {
  private audioCtx?: AudioContext
  private analyser?: AnalyserNode
  private data?: Uint8Array
  private raf = 0
  private prevEma = 0

  constructor(private vrm: VRM) {}

  /** start analysing the given stream */
  start(stream: MediaStream) {
    this.stop()
    this.audioCtx = new AudioContext()
    const source = this.audioCtx.createMediaStreamSource(stream)
    this.analyser = this.audioCtx.createAnalyser()
    this.analyser.fftSize = 1024
    source.connect(this.analyser)
    if (import.meta.env.VITE_DEBUG_AUDIO === 'true') {
      const debugGain = this.audioCtx.createGain()
      debugGain.gain.value = 0
      source.connect(debugGain).connect(this.audioCtx.destination)
    }
    this.data = new Uint8Array(this.analyser.frequencyBinCount)
    this.tick()
  }

  private tick = () => {
    this.update()
    this.raf = requestAnimationFrame(this.tick)
  }

  private update() {
    if (!this.analyser || !this.data) return
    this.analyser.getByteFrequencyData(this.data)
    let sum = 0
    for (let i = 0; i < this.data.length; i++) sum += this.data[i]
    const volume = sum / this.data.length / 255
    this.prevEma = mapVolumeToJaw(volume, this.prevEma)
    this.vrm.expressionManager?.setValue(VRMExpressionPresetName.A, this.prevEma)
  }

  /** stop lip sync and reset mouth */
  stop() {
    cancelAnimationFrame(this.raf)
    this.vrm.expressionManager?.setValue(VRMExpressionPresetName.A, 0)
    this.analyser?.disconnect()
    this.analyser = undefined
    this.data = undefined
    if (this.audioCtx) {
      this.audioCtx.close()
      this.audioCtx = undefined
    }
    this.prevEma = 0
  }
}
