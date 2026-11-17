#pragma once

#include <ArduinoJson.h>
#include <cstdint>
#include <optional>
#include <string_view>

namespace stackchan::notifications::payload {

class CompactJsonMatch {
public:
    explicit CompactJsonMatch(std::string_view input) : _remaining(input) {}

    std::size_t write(std::uint8_t byte) { return write(&byte, 1); }

    std::size_t write(const std::uint8_t* bytes, std::size_t size)
    {
        if (!_matches ||
            _remaining.substr(0, size) !=
                std::string_view(reinterpret_cast<const char*>(bytes), size)) {
            _matches = false;
            return 0;
        }
        _remaining.remove_prefix(size);
        return size;
    }

    bool complete() const { return _matches && _remaining.empty(); }

private:
    std::string_view _remaining;
    bool _matches = true;
};

inline std::string_view stringValue(JsonVariantConst value)
{
    const auto text = value.as<JsonString>();
    return text.isNull() ? std::string_view{} : std::string_view(text.c_str(), text.size());
}

inline int digits(std::string_view value)
{
    int result = 0;
    for (char c : value) {
        if (c < '0' || c > '9') {
            return -1;
        }
        result = result * 10 + (c - '0');
    }
    return result;
}

inline bool leapYear(int year)
{
    return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
}

// Accepts Coordinator ISO UTC with or without millisecond fraction.
inline std::optional<std::uint64_t> utcMillis(std::string_view value)
{
    const bool with_millis = value.size() == 24;
    if (!(value.size() == 20 || with_millis) || value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
        value[13] != ':' || value[16] != ':' || value.back() != 'Z') {
        return std::nullopt;
    }
    if (with_millis && value[19] != '.') {
        return std::nullopt;
    }
    if (!with_millis && value[19] != 'Z') {
        return std::nullopt;
    }
    const int year = digits(value.substr(0, 4));
    const int month = digits(value.substr(5, 2));
    const int day = digits(value.substr(8, 2));
    const int hour = digits(value.substr(11, 2));
    const int minute = digits(value.substr(14, 2));
    const int second = digits(value.substr(17, 2));
    const int millis = with_millis ? digits(value.substr(20, 3)) : 0;
    if (year < 1970 || month < 1 || month > 12 || day < 1 || hour < 0 || hour > 23 || minute < 0 ||
        minute > 59 || second < 0 || second > 59 || millis < 0) {
        return std::nullopt;
    }
    const int month_days[] = {31, leapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (day > month_days[month - 1]) {
        return std::nullopt;
    }
    const auto leapYearsBefore = [](int y) { return (y - 1) / 4 - (y - 1) / 100 + (y - 1) / 400; };
    std::uint64_t days = (year - 1970) * 365 + leapYearsBefore(year) - leapYearsBefore(1970) + day - 1;
    for (int i = 0; i < month - 1; ++i) {
        days += month_days[i];
    }
    return ((days * 24 + hour) * 60 * 60 + minute * 60 + second) * 1000 + millis;
}

}  // namespace stackchan::notifications::payload
