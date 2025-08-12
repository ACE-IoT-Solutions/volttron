# Platform Driver Agent Changelog

## [4.7.0] - 2025-01-14

### Added
- **Prometheus Metrics Enhancements**
  - New `device_configured_points` gauge to track total configured points per device
  - New `device_scraped_points` gauge to track successfully scraped points in last attempt
  - New `device_up` gauge for device status monitoring (1=up, 0=down)
  - Metrics initialization during device setup for consistency
  - Error handling for Prometheus metrics file writing

### Fixed
- **Prometheus Metrics**
  - Fixed `point_count` logic to properly differentiate between configured and scraped points
  - Properly set device status based on scrape success/failure
  - Added try-catch around metric file writing to prevent crashes

### Changed
- **Prometheus Metrics**
  - Renamed ambiguous `point_count` to more specific `device_scraped_points`
  - Added backwards compatibility alias for `point_count`
  - Enhanced debug logging for metrics operations

## [4.6.2] - Previous Release
- Base version before enhancements

---

## Summary of Metrics Available

### Performance Metrics
- `device_scrape_time_histogram` - Histogram of scrape times per device
- `device_scrape_time` - Gauge of last scrape time per device

### Error Tracking
- `device_error_count` - Counter of errors per device
- `failed_point_scrape` - Counter of failed point scrapes per point/device

### Device Status
- `device_up` - Gauge indicating device status (1=up, 0=down)
- `device_configured_points` - Gauge of total configured points per device
- `device_scraped_points` - Gauge of successfully scraped points in last attempt

### Usage Example

Prometheus queries for monitoring:
```promql
# Alert on device down
device_up{device="mydevice"} == 0

# Alert on partial data collection
(device_scraped_points / device_configured_points) < 0.9

# Track scrape performance
histogram_quantile(0.95, device_scrape_time_histogram)
```