/**
 * Seeded deterministic PRNG (sfc32 seeded through splitmix32).
 *
 * The Python reference uses numpy's PCG64. Bit-for-bit parity with numpy is an
 * intentional non-goal (see CONTROLLER_COMPATIBILITY.md); what matters is that a
 * seed fully determines every random draw so missions replay exactly.
 */
export class Rng {
  private a: number;
  private b: number;
  private c: number;
  private d: number;

  constructor(seed: number) {
    let s = seed >>> 0;
    const next = () => {
      s = (s + 0x9e3779b9) >>> 0;
      let z = s;
      z = Math.imul(z ^ (z >>> 16), 0x85ebca6b) >>> 0;
      z = Math.imul(z ^ (z >>> 13), 0xc2b2ae35) >>> 0;
      return (z ^ (z >>> 16)) >>> 0;
    };
    this.a = next();
    this.b = next();
    this.c = next();
    this.d = next();
    for (let i = 0; i < 12; i++) this.random();
  }

  /** Uniform float in [0, 1). */
  random(): number {
    const t = (((this.a + this.b) >>> 0) + this.d) >>> 0;
    this.d = (this.d + 1) >>> 0;
    this.a = this.b ^ (this.b >>> 9);
    this.b = (this.c + (this.c << 3)) >>> 0;
    this.c = (this.c << 21) | (this.c >>> 11);
    this.c = (this.c + t) >>> 0;
    return t / 4294967296;
  }

  /** Integer in [low, high). With one argument, [0, low). */
  integers(low: number, high?: number): number {
    if (high === undefined) {
      high = low;
      low = 0;
    }
    return low + Math.floor(this.random() * (high - low));
  }

  uniform(low: number, high: number): number {
    return low + this.random() * (high - low);
  }

  /** Box–Muller normal sample; always consumes exactly two draws. */
  normal(mean = 0, std = 1): number {
    const u1 = Math.max(this.random(), 1e-12);
    const u2 = this.random();
    if (std === 0) return mean;
    return mean + std * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }

  permutation(n: number): number[] {
    const values = Array.from({ length: n }, (_, i) => i);
    for (let i = n - 1; i > 0; i--) {
      const j = this.integers(i + 1);
      const tmp = values[i];
      values[i] = values[j];
      values[j] = tmp;
    }
    return values;
  }

  pick<T>(items: readonly T[]): T {
    return items[this.integers(items.length)];
  }
}

/** Deterministic 32-bit string hash (FNV-1a) used for seeds and rendezvous keys. */
export function hashString(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  // Final avalanche so neighbouring keys do not produce ordered hashes.
  h ^= h >>> 16;
  h = Math.imul(h, 0x7feb352d) >>> 0;
  h ^= h >>> 15;
  h = Math.imul(h, 0x846ca68b) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}
