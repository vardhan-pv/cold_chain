METRICS = ['starting_temperature_c','target_temperature_c','minimum_temperature_c',
    'cooldown_s','steady_state_temperature_c','humidity_pct','primary_current_a',
    'backup_current_a','heatsink_temperature_c','primary_detection_s','backup_activation_s',
    'recovery_s','rerouting_s','telemetry_success_pct','ml_inference_ms',
    'xgboost_f1','random_forest_f1','ensemble_f1']

def validation_report(device_id, records):
    measured={r['payload']['metric']:r['payload'] for r in reversed(records)
              if r['payload']['mode']=='HARDWARE'}
    return {'device_id':device_id,'hardware_status':'PENDING_HARDWARE',
        'note':'Operator-submitted evidence is not independent hardware certification.',
        'metrics':[{'metric':m,'value':measured.get(m,{}).get('value'),
            'status':'EVIDENCE_RECORDED' if m in measured else
                'UNAVAILABLE_NO_SENSOR' if m=='backup_current_a' else 'PENDING_HARDWARE',
            'evidence':measured.get(m,{}).get('evidence'),
            'measurement_source':'EXTERNAL_METER_REQUIRED' if m=='backup_current_a' else 'PROTOTYPE_TEST'} for m in METRICS],
        'submitted_records':records}
