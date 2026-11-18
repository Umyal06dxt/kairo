/** Sequential playback of base64 WAV sentences streamed from the server. */
export class AudioPlayer {
  private ctx: AudioContext | null = null;
  private queue: string[] = [];
  private playing = false;
  private generation = 0;

  /** Must be called from a user gesture at least once so browsers allow playback. */
  unlock(): void {
    this.ensure()?.resume?.().catch(() => {});
  }

  enqueue(b64: string): void {
    this.queue.push(b64);
    if (!this.playing) void this.next(this.generation);
  }

  stop(): void {
    this.generation++;
    this.queue = [];
    this.playing = false;
  }

  private ensure(): AudioContext | null {
    if (this.ctx) return this.ctx;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    this.ctx = Ctor ? new Ctor() : null;
    return this.ctx;
  }

  private async next(gen: number): Promise<void> {
    const item = this.queue.shift();
    const ctx = this.ensure();
    if (item === undefined || !ctx || gen !== this.generation) {
      this.playing = false;
      return;
    }
    this.playing = true;
    try {
      const bin = atob(item);
      const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
      const buf = await ctx.decodeAudioData(bytes.buffer);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.onended = () => void this.next(gen);
      src.start();
    } catch {
      void this.next(gen); // skip a sentence that fails to decode
    }
  }
}
