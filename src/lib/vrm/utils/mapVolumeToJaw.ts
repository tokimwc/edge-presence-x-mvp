export function mapVolumeToJaw(raw: number, prev: number) {
  const alpha = 0.25;                // EMA smoothing
  const ema   = raw * alpha + prev * (1 - alpha)
  return ema > 0.6 ? 0.8 : ema > 0.2 ? 0.4 : 0
}
