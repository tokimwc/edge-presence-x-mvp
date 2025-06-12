import { VRM, VRMExpressionPresetName } from '@pixiv/three-vrm'
import * as THREE from 'three'
import { gsap } from 'gsap'

/**
 * Handles idle blink and subtle gaze movement.
 */
export class IdleAnimation {
  private raf = 0
  private blinkTimer = 0
  private nextBlink = this.randomGauss(5, 1)
  private gazeTimer = 0
  private nextGaze = 4 + Math.random() * 2

  constructor(private vrm: VRM, private target: THREE.Object3D) {}

  start() { this.tick() }

  stop() { cancelAnimationFrame(this.raf) }

  private tick = () => {
    this.update(1 / 60)
    this.raf = requestAnimationFrame(this.tick)
  }

  private update(delta: number) {
    this.blinkTimer += delta
    if (this.blinkTimer > this.nextBlink) {
      this.vrm.expressionManager?.setValue(VRMExpressionPresetName.Blink, 1)
      setTimeout(() => this.vrm.expressionManager?.setValue(VRMExpressionPresetName.Blink, 0), 150)
      this.blinkTimer = 0
      this.nextBlink = this.randomGauss(5, 1)
    }

    this.gazeTimer += delta
    if (this.gazeTimer > this.nextGaze) {
      this.moveGaze()
      this.gazeTimer = 0
      this.nextGaze = 4 + Math.random() * 2
    }
  }

  private moveGaze() {
    const pos = new THREE.Vector3(
      (Math.random() - 0.5) * 0.2,
      1.4 + (Math.random() - 0.5) * 0.2,
      2.5
    )
    gsap.to(this.target.position, { x: pos.x, y: pos.y, z: pos.z, duration: 0.6, ease: 'quad.inOut' })
  }

  private randomGauss(mu = 0, sigma = 1): number {
    let u = 0, v = 0
    while (u === 0) u = Math.random()
    while (v === 0) v = Math.random()
    return mu + sigma * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
  }
}
