"""Journal-first ATT1 recovery and transactional simulated state publication."""
from copy import deepcopy
import hashlib
from pathlib import Path

from research_lab.att1_lifecycle_coordinator import replay_lifecycle, digest, canonical
from research_lab.att1_lifecycle_journal import LifecycleJournal
from research_lab.att1_lifecycle_profile import validate_profile

ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_FILES = (
    'research_lab/att1_lifecycle_profile.py', 'research_lab/att1_lifecycle_coordinator.py',
    'research_lab/att1_lifecycle_session.py', 'research_lab/att1_lifecycle_journal.py',
    'research_lab/att1_ets2s_lifecycle.py', 'research_lab/att1_ets2s_accounting.py',
)
HEADER_FIELDS = {'schema_id','event_id','kind','intent','profile_sha256','implementation_sha256'}


class SessionViolation(ValueError):
    """A restart cannot silently adopt another profile, intent or implementation."""


def implementation_hash():
    result=hashlib.sha256()
    for relative in IMPLEMENTATION_FILES:
        result.update(relative.encode('ascii')+b'\0')
        result.update((ROOT/relative).read_bytes())
    return result.hexdigest()


class LifecycleSession:
    def __init__(self,path,profile,*,intent=None):
        validate_profile(profile)
        self.profile=deepcopy(profile)
        self.journal=LifecycleJournal(path)
        self._implementation=implementation_hash()
        self._expected_intent=deepcopy(intent)
        records=self.journal.read()
        if not records:
            if intent is None:
                raise SessionViolation('missing journal; cannot reset a recovered book')
            header={'schema_id':'att1_lifecycle_event_v1','kind':'START','intent':deepcopy(intent),
                    'profile_sha256':profile['profile_sha256'],'implementation_sha256':self._implementation}
            header['event_id']='start:'+digest(header)
            _,result=self.journal.append_checked(header,self._replay)
        else:
            result=self._replay(records)
        self.receipt=result

    def _replay(self,records):
        if not records:
            raise SessionViolation('missing lifecycle header')
        header=records[0]
        if set(header)!=HEADER_FIELDS or header['schema_id']!='att1_lifecycle_event_v1' or header['kind']!='START':
            raise SessionViolation('invalid lifecycle header')
        unsigned={k:v for k,v in header.items() if k!='event_id'}
        if header['event_id']!='start:'+digest(unsigned):
            raise SessionViolation('header identity mismatch')
        if header['implementation_sha256']!=self._implementation:
            raise SessionViolation('implementation changed; explicit new epoch required')
        if header['profile_sha256']!=self.profile['profile_sha256']:
            raise SessionViolation('profile changed; explicit new epoch required')
        if self._expected_intent is not None and canonical(header['intent'])!=canonical(self._expected_intent):
            raise SessionViolation('restart intent conflict')
        receipt=replay_lifecycle(self.profile,header['intent'],list(records[1:]))
        if not receipt['admission']['accepted']:
            raise SessionViolation('admission rejected; no lifecycle book can be created')
        return receipt

    def apply(self,event):
        # Re-evaluate against latest rows under the journal's exclusive lock.
        # Only the durable result becomes visible in memory. A torn write or a
        # crash before this assignment leaves recovery authority in the journal.
        _,result=self.journal.append_checked(event,self._replay)
        self.receipt=result
        return deepcopy(result)

    def refresh(self):
        result=self._replay(self.journal.read())
        self.receipt=result
        return deepcopy(result)
