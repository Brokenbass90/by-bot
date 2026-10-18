from research_lab.alpaca_monthly_notifications_v1 import event_delivery


def test_existing_channel_deduplicates_failure_recovery_and_delivery_test(tmp_path):
    c=dict(output_root=str(tmp_path/'alerts'),scope_label='Trading OS Monthly ORDERS_OFF')
    sent=[]
    def send(e):sent.append(e);return dict(delivered=True,message_id=len(sent))
    assert event_delivery(c,now_ms=1000000000000,sender=send)['status']=='QUIET'
    assert event_delivery(c,now_ms=1000000000000,failure_code='MONTHLY_SOURCE_MISSING',sender=send)['status']=='DELIVERED'
    assert event_delivery(c,now_ms=1000000001000,failure_code='MONTHLY_SOURCE_MISSING',sender=send)['status']=='ALREADY_RECORDED'
    assert event_delivery(c,now_ms=1000000002000,sender=send)['status']=='DELIVERED'
    assert event_delivery(c,now_ms=1000000003000,sender=send)['status']=='QUIET'
    assert event_delivery(c,now_ms=1000000003000,test=True,sender=send)['status']=='DELIVERED'
    assert event_delivery(c,now_ms=1000000004000,test=True,sender=send)['status']=='ALREADY_RECORDED'
    assert [e['kind'] for e in sent]==['CRITICAL','RECOVERED','DELIVERY_TEST']


def test_unknown_notification_delivery_does_not_repeat_after_restart(tmp_path):
    c=dict(output_root=str(tmp_path/'alerts'));sent=[]
    def lost(e):sent.append(e);raise TimeoutError('simulated accepted response lost')
    assert event_delivery(c,now_ms=1000000000000,test=True,sender=lost)['status']=='DELIVERY_UNKNOWN_NO_RETRY'
    assert event_delivery(c,now_ms=1000000001000,test=True,sender=lost)['status']=='ALREADY_RECORDED'
    assert len(sent)==1


def test_source_incident_cannot_be_recovered_by_manager_and_recurring_failure_alerts_again(tmp_path):
    c=dict(output_root=str(tmp_path/'alerts'));sent=[]
    def send(e):sent.append(e);return dict(delivered=True)
    base=1000000000000
    event_delivery(c,now_ms=base,component='source',failure_code='SOURCE_MISSING',sender=send)
    assert event_delivery(c,now_ms=base+1000,component='manager',sender=send)['status']=='QUIET'
    assert event_delivery(c,now_ms=base+2000,component='source',failure_code='SOURCE_MISSING',sender=send)['status']=='ALREADY_RECORDED'
    event_delivery(c,now_ms=base+3000,component='source',sender=send)
    assert event_delivery(c,now_ms=base+4000,component='source',failure_code='SOURCE_MISSING',sender=send)['status']=='DELIVERED'
    assert [e['kind'] for e in sent]==['CRITICAL','RECOVERED','CRITICAL']
    assert sent[0]['incident_id']!=sent[-1]['incident_id']
