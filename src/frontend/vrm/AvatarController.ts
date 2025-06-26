import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader';
import {
  VRM,
  VRMLoaderPlugin,
  VRMUtils,
  VRMExpressionPresetName,
} from '@pixiv/three-vrm';

export class AvatarController {
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private loader: GLTFLoader;
  private vrm?: VRM;
  private lookAtTarget: THREE.Object3D = new THREE.Object3D();

  private clock = new THREE.Clock();
  private frameId = 0;

  private audioContext?: AudioContext;
  private analyser?: AnalyserNode;
  private dataArray?: Uint8Array;

  private blinkTimer = 0;
  private nextBlink = 2 + Math.random() * 3;

  get vrmModel() {
    return this.vrm;
  }

  public setPose(pose: any) {
    if (this.vrm?.humanoid) {
      this.vrm.humanoid.setRawPose(pose);
    }
  }

  constructor(private canvas: HTMLCanvasElement) {
    this.renderer = new THREE.WebGLRenderer({ canvas, alpha: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(
      30,
      canvas.clientWidth / canvas.clientHeight,
      0.1,
      100
    );
    this.camera.position.set(0, 1.3, 2.5);

    this.loader = new GLTFLoader();
    this.loader.register((parser) => new VRMLoaderPlugin(parser));

    const amb = new THREE.AmbientLight(0xffffff, 1.2)
    const dir = new THREE.DirectionalLight(0xffffff, 3)
    dir.position.set(2, 3, 5)
    this.scene.add(amb, dir)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping

    this.scene.add(this.lookAtTarget);
  }

  async load(url: string) {
    const gltf = await this.loader.loadAsync(url);
    this.vrm = gltf.userData.vrm as VRM;
    VRMUtils.rotateVRM0(this.vrm); // モデルの向きを調整
    this.scene.add(this.vrm.scene);
    this.start();
  }

  private start() {
    const loop = () => {
      const delta = this.clock.getDelta();
      this.update(delta);
      this.renderer.render(this.scene, this.camera);
      this.frameId = requestAnimationFrame(loop);
    };
    loop();
  }

  dispose() {
    cancelAnimationFrame(this.frameId);
    if (this.audioContext) {
      this.audioContext.close();
    }
  }

  startLipSync(stream: MediaStream) {
    this.audioContext?.close();
    this.audioContext = new AudioContext();
    const source = this.audioContext.createMediaStreamSource(stream);
    this.analyser = this.audioContext.createAnalyser();
    this.analyser.fftSize = 1024;
    source.connect(this.analyser);
    this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
  }

  stopLipSync() {
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = undefined;
      this.analyser = undefined;
    }
    this.setMouth(0);
  }

  private update(delta: number) {
    if (this.vrm) {
      this.vrm.update(delta);
    }

    this.updateLipSync();
    this.updateBlink(delta);
  }

  private updateLipSync() {
    if (!this.analyser || !this.dataArray) return;
    this.analyser.getByteFrequencyData(this.dataArray);
    let sum = 0;
    for (let i = 0; i < this.dataArray.length; i++) {
      sum += this.dataArray[i];
    }
    const volume = sum / this.dataArray.length / 255;
    const mouth = Math.min(1, Math.max(0, volume * 2));
    this.setMouth(mouth);
  }

  private setMouth(value: number) {
    if (!this.vrm) return;
    this.vrm.expressionManager?.setValue(
      VRMExpressionPresetName.Aa,
      value * 0.7
    );
    this.vrm.expressionManager?.setValue(
      VRMExpressionPresetName.Oh,
      value * 0.1
    );
  }

  setExpression(name: VRMExpressionPresetName, value: number) {
    if (!this.vrm) return;
    this.vrm.expressionManager?.setValue(name, value);
  }

  private updateBlink(delta: number) {
    if (!this.vrm) return;
    this.blinkTimer += delta;
    if (this.blinkTimer > this.nextBlink) {
      this.vrm.expressionManager?.setValue(VRMExpressionPresetName.Blink, 1);
      setTimeout(() => {
        this.vrm?.expressionManager?.setValue(VRMExpressionPresetName.Blink, 0);
      }, 150);
      this.blinkTimer = 0;
      this.nextBlink = 2 + Math.random() * 3;
    }
  }
}
