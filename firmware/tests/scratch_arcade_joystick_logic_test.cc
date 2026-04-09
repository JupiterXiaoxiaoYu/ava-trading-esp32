#include <cstdlib>
#include <iostream>

#include "../main/boards/scratch-arcade/joystick_axis.h"

using scratch_arcade::AxisDirection;
using scratch_arcade::AxisThresholds;
using scratch_arcade::DecideAxisDirection;

static void ExpectEq(AxisDirection actual, AxisDirection expected, const char* name) {
    if (actual != expected) {
        std::cerr << "FAIL: " << name << " expected=" << static_cast<int>(expected)
                  << " actual=" << static_cast<int>(actual) << std::endl;
        std::exit(1);
    }
}

int main() {
    const AxisThresholds thresholds{.center = 1900, .press_delta = 550, .release_delta = 250};

    ExpectEq(DecideAxisDirection(1900, AxisDirection::kCenter, thresholds),
             AxisDirection::kCenter, "center stays center");
    ExpectEq(DecideAxisDirection(2600, AxisDirection::kCenter, thresholds),
             AxisDirection::kPositive, "high raw enters positive");
    ExpectEq(DecideAxisDirection(1200, AxisDirection::kCenter, thresholds),
             AxisDirection::kNegative, "low raw enters negative");

    ExpectEq(DecideAxisDirection(2350, AxisDirection::kPositive, thresholds),
             AxisDirection::kPositive, "positive hold survives until release threshold");
    ExpectEq(DecideAxisDirection(2100, AxisDirection::kPositive, thresholds),
             AxisDirection::kCenter, "positive releases near center");
    ExpectEq(DecideAxisDirection(1200, AxisDirection::kPositive, thresholds),
             AxisDirection::kNegative, "positive can flip to negative");

    ExpectEq(DecideAxisDirection(1450, AxisDirection::kNegative, thresholds),
             AxisDirection::kNegative, "negative hold survives until release threshold");
    ExpectEq(DecideAxisDirection(1750, AxisDirection::kNegative, thresholds),
             AxisDirection::kCenter, "negative releases near center");
    ExpectEq(DecideAxisDirection(2700, AxisDirection::kNegative, thresholds),
             AxisDirection::kPositive, "negative can flip to positive");

    std::cout << "scratch_arcade_joystick_logic_test: PASS" << std::endl;
    return 0;
}
