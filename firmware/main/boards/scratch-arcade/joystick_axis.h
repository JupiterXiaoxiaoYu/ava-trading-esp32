#pragma once

namespace scratch_arcade {

enum class AxisDirection {
    kNegative = -1,
    kCenter = 0,
    kPositive = 1,
};

struct AxisThresholds {
    int center;
    int press_delta;
    int release_delta;
};

inline AxisDirection DecideAxisDirection(int raw, AxisDirection current,
                                         const AxisThresholds& thresholds) {
    const int positive_press = thresholds.center + thresholds.press_delta;
    const int negative_press = thresholds.center - thresholds.press_delta;
    const int positive_release = thresholds.center + thresholds.release_delta;
    const int negative_release = thresholds.center - thresholds.release_delta;

    if (raw >= positive_press) {
        return AxisDirection::kPositive;
    }
    if (raw <= negative_press) {
        return AxisDirection::kNegative;
    }

    if (current == AxisDirection::kPositive) {
        return raw >= positive_release ? AxisDirection::kPositive : AxisDirection::kCenter;
    }
    if (current == AxisDirection::kNegative) {
        return raw <= negative_release ? AxisDirection::kNegative : AxisDirection::kCenter;
    }
    return AxisDirection::kCenter;
}

}  // namespace scratch_arcade
