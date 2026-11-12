/* Resamples microphone input to 16 kHz and posts bounded 40 ms PCM float blocks. */
class JarvisCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
    this.samples = new Float32Array(640);
    this.offset = 0;
    this.credits = 1;
    this.port.onmessage = event => {
      if (event.data && event.data.type === "credit") this.credits = 1;
    };
  }

  process(inputs, outputs) {
    const input = inputs[0] && inputs[0][0];
    const output = outputs[0] && outputs[0][0];
    if (!input) return true;
    if (output) output.set(input);

    for (let i = 0; i < input.length; i += 1) {
      this.sum += input[i];
      this.count += 1;
      this.phase += 16000;
      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;
        this.samples[this.offset] = this.sum / this.count;
        this.offset += 1;
        this.sum = 0;
        this.count = 0;
        if (this.offset === this.samples.length) {
          const completed = this.samples;
          this.samples = new Float32Array(640);
          this.offset = 0;
          if (this.credits > 0) {
            this.credits = 0;
            this.port.postMessage(completed, [completed.buffer]);
          }
        }
      }
    }
    return true;
  }
}

registerProcessor("jarvis-capture", JarvisCaptureProcessor);
