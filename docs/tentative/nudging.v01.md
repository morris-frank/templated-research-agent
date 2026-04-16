# Feature

> **Voice identity layer** — amical knows *what* you said but not *how* you said it. A speaker profile could track your baseline pace, filler-word density, vocal energy, and even flag when you sound unusually uncertain or rushed. This feeds into real-time coaching nudges ("you're speaking 30% faster than your baseline — slow down") and longitudinal reports on your communication patterns over time.

**Validation before personalization**

The baseline model is only valuable if the absolute thresholds first confirm that the *signal itself is meaningful* — that pace and pitch features actually correlate with something the user notices and cares about. If you build the personalization layer first and the nudges feel wrong, you don't know if the problem is bad thresholds, bad features, or bad baseline modeling. Absolute thresholds isolate the first question cleanly.

**What "validation" actually means here**

The risk with absolute thresholds isn't that they'll be wrong for everyone — it's that they'll be wrong for *specific people* in ways that feel insulting. A fast natural speaker gets nudged constantly. A soft-spoken person never gets nudged despite being clearly stressed. So the validation goal isn't "do the thresholds fire" but "when they fire, does the user agree something was happening?"

The simplest mechanism: after each nudge, show a tiny thumbs up / thumbs down. No prompt, no explanation — just a passive signal collector. After 20–30 sessions across a small group of users, you'll know whether the signal-to-noise ratio justifies the personalization investment.

**Sensible starting thresholds**

Research on speech and cognitive load gives reasonable priors:

Pace above ~180wpm is where comprehension starts dropping for listeners, and where speakers report feeling rushed in retrospect. A floor of 160wpm is probably safer to avoid over-triggering. Pitch variance is harder to set absolutely — it's inherently relative — so this dimension probably shouldn't fire at all in the absolute phase, and waits for the baseline model. RMS energy drop of more than ~40% sustained over 30 seconds is a meaningful signal. Filler density above roughly one filler per 15 words is noticeable to listeners.

**The concrete recommendation**

Ship v1 with pace-only nudges at an absolute threshold, a passive thumbs-up/down collector on each nudge, and a settings toggle to turn the whole thing off. That's the minimum surface area to learn whether users find the signal valuable. Pitch and filler density can join in v2 once you have signal that pace nudges are landing well. The baseline model becomes v3 — built on real user data, not assumptions.

The temptation will be to ship the full vision. Resist it. If the absolute-threshold pace nudge doesn't feel useful, none of the rest of the stack matters.  

out of scope for v1  
— pitch and energy features (wait for pace signal validation)  
— personal baseline model (needs multi-session data first)  
— speaker diarisation (separate feature, different audio stack)  
— nudge history view / analytics (build after thumbs signal proves value)  
— meeting-only scope restriction (run in dictation too, more data faster)  
— DSP audio tap (no new audio processing in v1 at all)  

**The key constraint that keeps this simple**

No new audio processing whatsoever. Whisper already outputs word-level timestamps in `TranscriptSegment` — the pace calculator just reads those. The entire feature is derived from data that already exists in the pipeline, which means zero new capture code, zero new native dependencies, zero risk to the recording path.

**Step 2 in detail — the pace calculator**

A rolling 20-second window is the right choice over a cumulative average. Cumulative average smooths everything into meaninglessness — if you spoke fast for 30 seconds 10 minutes ago, it still drags the number up. The rolling window reflects what's happening *now*.

```ts
// pace-calculator.ts
export function calculateWpm(
  segments: { word: string; startMs: number; endMs: number }[],
  windowMs = 20_000
): number {
  const now = segments.at(-1)?.endMs ?? 0
  const windowStart = now - windowMs
  const inWindow = segments.filter(s => s.startMs >= windowStart)
  if (inWindow.length < 5) return 0  // too few words to be meaningful
  const elapsedMinutes = (now - inWindow[0].startMs) / 60_000
  return Math.round(inWindow.length / elapsedMinutes)
}

```

The `< 5 words` guard matters — without it you get absurd wpm numbers at the start of a recording when there are only two words in the window.

**Step 3 in detail — the cooldown gate**

The consecutive-windows check (fire only after 3 windows above threshold) eliminates single-sentence bursts from triggering anything. At 10-second windows, that's 30 seconds of sustained fast pace before a nudge fires. The 2-minute cooldown after each nudge prevents the feature from becoming noise. Both numbers belong in the settings schema so they're tunable without a code change.

```ts
// nudge-engine.ts
export class NudgeEngine {
  private consecutiveCount = 0
  private lastNudgedAt = 0

  check(wpm: number, threshold: number, now = Date.now()): boolean {
    if (wpm > threshold) {
      this.consecutiveCount++
    } else {
      this.consecutiveCount = 0
    }
    const cooldownClear = now - this.lastNudgedAt > 120_000
    if (this.consecutiveCount >= 3 && cooldownClear) {
      this.lastNudgedAt = now
      this.consecutiveCount = 0
      return true
    }
    return false
  }
}

```

Pure class, no imports, trivially unit-testable. The threshold comes in from settings at call time — the engine knows nothing about configuration.

**Step 4 — what to log**

The thumbs up/down is the whole point of v1 existing. Each nudge fires a row into a new `nudge_feedback` table:

```
nudge_feedback: id, firedAt, wpmAtFire, userFeedback ('up' | 'down' | null), sessionType ('dictation' | 'meeting')

```

`userFeedback null` means the toast auto-dismissed without interaction — that's still a data point (not annoying enough to dismiss, not useful enough to upvote). After 30–40 entries you'll have a clear picture: if 70%+ of `up` responses cluster at wpm > 170, shift the default threshold up. If most nudges are dismissed without feedback, the feature isn't landing yet.

**What iteration looks like after v1**

The next decision point is 4–6 weeks after shipping to a handful of users. If thumbs-up rate is above ~50%, the signal is real and you tune the threshold toward personalization. If it's below 30%, you investigate whether the window size, threshold, or message copy is the problem — before touching any new feature. The out-of-scope list stays frozen until that question is answered.