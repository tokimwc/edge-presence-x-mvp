import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import {
  VRM,
  VRMLoaderPlugin,
  VRMUtils,
  VRMExpressionPresetName,
} from '@pixiv/three-vrm';

export class AvatarController {
  private container: HTMLDivElement;
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;
  private loader: GLTFLoader;
  private vrm?: VRM;
  private lookAtTarget: THREE.Object3D = new THREE.Object3D();
  private _initialPose: any | null = null;

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
      this._initialPose = pose;
    }
  }

  constructor(container: HTMLDivElement) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    this.renderer.setPixelRatio(window.devicePixelRatio);
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();

    const aspect = container.clientWidth / container.clientHeight;
    this.camera = new THREE.PerspectiveCamera(30, aspect, 0.1, 20);
    this.camera.position.set(0, 1.3, 2.5);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableRotate = false;
    this.controls.enablePan = true;
    this.controls.enableZoom = true;
    this.controls.minDistance = 1;
    this.controls.maxDistance = 5;
    this.controls.target.set(0, 1.1, 0);
    this.controls.update();

    this.loader = new GLTFLoader();
    this.loader.register((parser) => new VRMLoaderPlugin(parser));

    const amb = new THREE.AmbientLight(0xffffff, 1.2);
    const dir = new THREE.DirectionalLight(0xffffff, 3);
    dir.position.set(2, 3, 5);
    this.scene.add(amb, dir);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;

    this.scene.add(this.lookAtTarget);
  }

  public resize() {
    if (!this.container) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;

    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();

    this.updateBackgroundTexture();
  }

  async load(url: string) {
    return new Promise((resolve, reject) => {
      this.loader.load(
        url,
        (gltf) => {
          this.vrm = gltf.userData.vrm as VRM;
          VRMUtils.rotateVRM0(this.vrm);
          this.scene.add(this.vrm.scene);

          const head = this.vrm.humanoid?.getBoneNode('head');
          if (head) {
            head.getWorldPosition(this.controls.target);
            this.camera.position.y = this.controls.target.y;
          }

          this.start();
          resolve(gltf);
        },
        undefined,
        reject
      );
    });
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

  public setBackground(imageUrl: string) {
    if (this.scene.background && (this.scene.background as THREE.Texture).isTexture) {
      (this.scene.background as THREE.Texture).dispose();
    }
    const textureLoader = new THREE.TextureLoader();
    textureLoader.load(imageUrl, (texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      this.scene.background = texture;
      this.updateBackgroundTexture();
    });
  }

  private updateBackgroundTexture() {
    const texture = this.scene.background as THREE.Texture;
    if (!texture || !texture.isTexture || !texture.image) {
      return;
    }

    const canvas = this.renderer.domElement;
    const canvasAspect = canvas.clientWidth / canvas.clientHeight;
    const imageAspect = texture.image.width / texture.image.height;

    if (canvasAspect > imageAspect) {
      texture.repeat.set(1, 1);
      const newAspect = imageAspect / canvasAspect;
      texture.repeat.y = newAspect;
      texture.offset.y = (1 - newAspect) / 2;
      texture.offset.x = 0;
    } else {
      texture.repeat.set(1, 1);
      const newAspect = canvasAspect / imageAspect;
      texture.repeat.x = newAspect;
      texture.offset.x = (1 - newAspect) / 2;
      texture.offset.y = 0;
    }
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
    
    if (this._initialPose && this.vrm?.humanoid) {
      this.vrm.humanoid.setRawPose(this._initialPose);
    }
    
    this.controls.update();
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
