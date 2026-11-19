#pragma once
#include <cstdint>

struct HallPulseState {
  int64_t lastPulseUs;
  int64_t periodUs;
  int64_t rawPeriodUs;
  uint32_t acceptedPulses;
  uint32_t rejectedPulses;
};

class HallPulseFilter {
 public:
  static constexpr unsigned int WINDOW_SIZE = 3;

  HallPulseFilter(int64_t minIntervalUs, int64_t timeoutUs, double minPeriodRatio)
      : minIntervalUs_(minIntervalUs), timeoutUs_(timeoutUs), minPeriodRatio_(minPeriodRatio) {}

  // Chamado na interrupção; sem alocação de memória.
  void observe(int64_t nowUs) {
    const int64_t rawElapsed = nowUs - lastRawPulseUs_;
    rawPeriodUs_ = lastRawPulseUs_ > 0 && rawElapsed <= timeoutUs_ ? rawElapsed : 0;
    lastRawPulseUs_ = nowUs;

    const int64_t elapsed = nowUs - lastPulseUs_;
    if (lastPulseUs_ == 0 || elapsed > timeoutUs_) {
      count_ = 0;
      next_ = 0;
      lastPulseUs_ = nowUs;
      ++acceptedPulses_;
      return;
    }

    if (elapsed < minIntervalUs_ ||
        (count_ == WINDOW_SIZE && elapsed < medianPeriod() * minPeriodRatio_)) {
      ++rejectedPulses_;
      return;
    }

    periods_[next_] = elapsed;
    next_ = (next_ + 1) % WINDOW_SIZE;
    if (count_ < WINDOW_SIZE) ++count_;
    lastPulseUs_ = nowUs;
    ++acceptedPulses_;
  }

  // Copiar com a mesma proteção usada pela interrupção.
  HallPulseState snapshot(int64_t nowUs) const {
    const bool fresh = lastPulseUs_ > 0 && nowUs - lastPulseUs_ <= timeoutUs_;
    return {
      lastPulseUs_,
      fresh && count_ == WINDOW_SIZE ? medianPeriod() : 0,
      lastRawPulseUs_ > 0 && nowUs - lastRawPulseUs_ <= timeoutUs_ ? rawPeriodUs_ : 0,
      acceptedPulses_,
      rejectedPulses_,
    };
  }

 private:
  int64_t medianPeriod() const {
    int64_t a = periods_[0], b = periods_[1], c = periods_[2];
    if (a > b) { const int64_t value = a; a = b; b = value; }
    if (b > c) { const int64_t value = b; b = c; c = value; }
    return a > b ? a : b;
  }

  const int64_t minIntervalUs_;
  const int64_t timeoutUs_;
  const double minPeriodRatio_;
  int64_t periods_[WINDOW_SIZE] = {};
  unsigned int count_ = 0;
  unsigned int next_ = 0;
  int64_t lastPulseUs_ = 0;
  int64_t lastRawPulseUs_ = 0;
  int64_t rawPeriodUs_ = 0;
  uint32_t acceptedPulses_ = 0;
  uint32_t rejectedPulses_ = 0;
};
