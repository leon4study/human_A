{
    "timestamp": "2026-03-15 14:32:00",
    "overall_alarm_level": 2,
    "overall_status": "Warning 🟠",
    "spike_info": {
        "is_spike": true,
        "is_startup_spike": false,
        "is_anomaly_spike": true,
    },
    "domain_reports": {
        "motor": {
            "metrics": {
                "current_mse": 0.084231,
                "train_loss": 0.012,
                "val_loss": 0.015,
            },
            "alarm": {"level": 2, "label": "Warning 🟠"},
            "global_thresholds": {
                "caution": 0.032145,
                "warning": 0.061280,
                "critical": 0.154900,
            },
            "rca_top3": [
                {"feature": "motor_current_a", "contribution": 47.3},
                {"feature": "rpm_stability_index", "contribution": 28.1},
                {"feature": "vibration_rms", "contribution": 12.6},
            ],
            "feature_details": [
                {
                    "name": "motor_current_a",
                    "actual_value": 18.42,
                    "expected_value": 14.10,
                    "bands": {
                        "caution_upper": 15.20,
                        "caution_lower": 13.00,
                        "warning_upper": 16.30,
                        "warning_lower": 11.90,
                        "critical_upper": 17.40,
                        "critical_lower": 10.80,
                    },
                }
            ],
            "target_reference_profiles": {
                "motor_current_a": {
                    "target_threshold_basis": "target_caution_band_1sigma",
                    "target_lines": {
                        "normal": 14.10,
                        "caution": {"lower": 13.00, "upper": 15.20},
                        "warning": {"lower": 11.90, "upper": 16.30},
                        "critical": {"lower": 10.80, "upper": 17.40},
                        "std": 1.10,
                        "training_min": 10.5,
                        "training_max": 17.2,
                    },
                    "normal_sample_count": 8421,
                    "related_feature_lines": {"rpm_stability_index": {"...": "..."}},
                }
            },
        },
        "hydraulic": {
            "metrics": {"current_mse": 0.011},
            "alarm": {"level": 0, "label": "Normal"},
            "global_thresholds": {"...": "..."},
            "rca_top3": [],
            "feature_details": [],
            "target_reference_profiles": {},
        },
        "nutrient": {"alarm": {"level": 0, "label": "Normal"}, "...": "..."},
        "zone_drip": {"alarm": {"level": 0, "label": "Normal"}, "...": "..."},
    },
    "action_required": "System check recommended",
}
