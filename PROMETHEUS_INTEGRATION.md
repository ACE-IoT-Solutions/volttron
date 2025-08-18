# Prometheus Metrics Integration

## Overview

The VOLTTRON Platform Driver Agent now includes comprehensive Prometheus metrics support for monitoring device health, performance, and data collection in production environments.

## Features

### Performance Metrics
- **device_scrape_time_histogram**: Histogram of time taken to scrape each device (buckets: 5ms to 30s)
- **device_scrape_time**: Gauge showing last scrape time for each device

### Error Tracking
- **device_error_count**: Counter of errors per device
- **failed_point_scrape**: Counter of failed point scrapes per device and point

### Point Tracking
- **device_configured_points**: Total number of configured points per device
- **device_scraped_points**: Number of points successfully scraped in last attempt
- **device_up**: Device status indicator (1=up, 0=down)

## Configuration

### Metrics File Location
By default, metrics are written to:
```
/opt/packages/prometheus_exporter/scrape_files/scrape_metrics.prom
```

### Installation Requirements
The prometheus-client library is now included in requirements:
```bash
prometheus-client==0.20.0
```

## Usage

### Enabling Metrics
Metrics are automatically enabled when the Platform Driver Agent starts. The agent periodically flushes metrics to the configured file every 10 seconds.

### Prometheus Configuration
Add the following to your Prometheus configuration to scrape VOLTTRON metrics:

```yaml
scrape_configs:
  - job_name: 'volttron'
    static_configs:
      - targets: ['localhost:9090']
    file_sd_configs:
      - files:
        - '/opt/packages/prometheus_exporter/scrape_files/scrape_metrics.prom'
```

### Grafana Dashboard
Create dashboards to visualize:
- Device up/down status
- Scrape performance over time
- Error rates per device
- Point collection success rates

## Example Metrics Output

```
# HELP device_scrape_time_histogram Time taken to scrape given device - histogram
# TYPE device_scrape_time_histogram histogram
device_scrape_time_histogram_bucket{device="campus/building1/ahu1",le="0.005"} 0
device_scrape_time_histogram_bucket{device="campus/building1/ahu1",le="0.01"} 2
device_scrape_time_histogram_bucket{device="campus/building1/ahu1",le="0.025"} 5
device_scrape_time_histogram_bucket{device="campus/building1/ahu1",le="+Inf"} 10
device_scrape_time_histogram_count{device="campus/building1/ahu1"} 10
device_scrape_time_histogram_sum{device="campus/building1/ahu1"} 0.125

# HELP device_up Device status: 1=up, 0=down
# TYPE device_up gauge
device_up{device="campus/building1/ahu1"} 1

# HELP device_configured_points Total number of configured points per device
# TYPE device_configured_points gauge
device_configured_points{device="campus/building1/ahu1"} 150

# HELP device_scraped_points Number of points successfully scraped in last attempt
# TYPE device_scraped_points gauge
device_scraped_points{device="campus/building1/ahu1"} 148
```

## Troubleshooting

### Metrics Not Appearing
1. Check that the metrics file directory exists and has write permissions
2. Verify prometheus-client is installed: `pip show prometheus-client`
3. Check Platform Driver Agent logs for metric write errors

### High Memory Usage
If experiencing high memory usage with many devices:
1. Consider increasing the flush interval
2. Monitor the size of the metrics file
3. Implement metric retention policies in Prometheus

## Migration from Previous Versions

The `point_count` metric has been deprecated and replaced with:
- `device_configured_points`: Total configured points
- `device_scraped_points`: Successfully scraped points

The old `point_count` metric is aliased to `device_scraped_points` for backwards compatibility.

## Additional Drivers

This integration also includes support for new device drivers:
- **Spirae Wave**: Renewable energy monitoring
- **modbus_enhanced**: Advanced Modbus with gateway support
- **Candidus, CTA Local, Desigo API**: Building automation
- **EthernetIP, Haystack API**: Industrial protocols
- **OpConnect, Shelly EM, SolarK**: Energy management
- **Venstar**: Thermostat control

## Version Information

- Platform Driver Agent: v4.6.2
- Prometheus Client: v0.20.0
- Python: 3.10+