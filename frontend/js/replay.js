/* Plays a recorded run through an AgentFlow at a readable pace, with pause, step and seek.
   Used by the home page and the run trace page. The events are never changed; only the
   pauses between them are chosen here. */
(function (global) {
  function Replay(flow, events, opts = {}) {
    this.flow = flow; this.events = events; this.opts = opts;
    this.i = 0; this.playing = false; this.speed = opts.speed || 1; this.timer = null;
  }
  // How long to stay on a message before the next one, by kind (milliseconds at 1x).
  Replay.prototype.pause = function (e) {
    if (this.opts.pauseFor) { const p = this.opts.pauseFor(e); if (p != null) return p; }
    if (e.type === 'tool_result') return 250;
    if (e.type === 'tool_call') return 650;
    if (e.type === 'task') return 900;
    return 2000;
  };
  Replay.prototype.show = function (k, animate) {
    const e = this.events[k];
    if (!e) return;
    this.flow.apply(e, {animate});
    if (this.opts.onEvent) this.opts.onEvent(e, k, animate);
  };
  Replay.prototype.tick = function () {
    clearTimeout(this.timer);
    if (!this.playing) return;
    if (this.i >= this.events.length) {
      this.setPlaying(false);
      if (this.opts.onEnd) this.opts.onEnd();
      return;
    }
    const k = this.i++;
    this.show(k, true);
    if (this.opts.onProgress) this.opts.onProgress(this.i);
    this.timer = setTimeout(() => this.tick(), this.pause(this.events[k]) / this.speed);
  };
  Replay.prototype.setPlaying = function (on) {
    this.playing = on;
    if (this.opts.onState) this.opts.onState(on);
    if (on) { if (this.i >= this.events.length) this.seek(0); this.tick(); } else clearTimeout(this.timer);
  };
  Replay.prototype.toggle = function () { this.setPlaying(!this.playing); };
  /* Jump so that the first n events have happened (drawn without animation). */
  Replay.prototype.seek = function (n) {
    clearTimeout(this.timer);
    n = Math.max(0, Math.min(this.events.length, n));
    this.flow.reset();
    if (this.opts.onReset) this.opts.onReset();
    for (let k = 0; k < n; k++) this.show(k, false);
    this.i = n;
    if (this.opts.onProgress) this.opts.onProgress(n);
    if (this.playing) this.timer = setTimeout(() => this.tick(), 400);
  };
  Replay.prototype.step = function (d) {
    const was = this.playing;
    this.setPlaying(false);
    if (d > 0 && this.i < this.events.length) {
      const k = this.i++;
      this.show(k, true);
      if (this.opts.onProgress) this.opts.onProgress(this.i);
    } else if (d < 0) this.seek(this.i - 1);
    return was;
  };
  global.Replay = Replay;
})(window);
