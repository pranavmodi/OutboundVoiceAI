"""Mock patient provider simulating PatientModule database."""
from datetime import datetime, timedelta
from typing import Optional
from app.models import Patient, Language, IntakeStatus


class MockPatientProvider:
    """Simulates PatientModule database with outbound call queue."""

    def __init__(self):
        self._patients: dict[str, Patient] = {}
        self._load_sample_data()

    def _load_sample_data(self):
        """Load sample patient data for testing."""
        now = datetime.now()

        sample_patients = [
            # Priority 1: Abandoned + never AI-called
            Patient(
                patient_id="PRE001",
                name="John Smith",
                phone="555-0101",
                language=Language.ENGLISH,
                order_id="ORD001",
                order_created=now - timedelta(days=1),
                has_abandoned_before=True,
                ai_called_before=False,
                due_by=now + timedelta(days=1),
            ),
            # Priority 1: Abandoned + never AI-called (Spanish)
            Patient(
                patient_id="PRE002",
                name="Maria Garcia",
                phone="555-0102",
                language=Language.SPANISH,
                order_id="ORD002",
                order_created=now - timedelta(days=2),
                has_abandoned_before=True,
                ai_called_before=False,
                due_by=now,
            ),
            # Priority 2: Abandoned + AI-called before
            Patient(
                patient_id="PRE003",
                name="Robert Johnson",
                phone="555-0103",
                language=Language.ENGLISH,
                order_id="ORD003",
                order_created=now - timedelta(days=1),
                has_abandoned_before=True,
                ai_called_before=True,
                attempt_count=1,
                last_attempt_at=now - timedelta(hours=8),
                last_outcome="no_answer",
                due_by=now + timedelta(days=1),
            ),
            # Priority 3: Never AI-called + called in before
            Patient(
                patient_id="PRE004",
                name="Emily Davis",
                phone="555-0104",
                language=Language.ENGLISH,
                order_id="ORD004",
                order_created=now - timedelta(hours=12),
                has_called_in_before=True,
                ai_called_before=False,
                due_by=now + timedelta(days=2),
            ),
            # Priority 4: Never AI-called + never called in
            Patient(
                patient_id="PRE005",
                name="Michael Wilson",
                phone="555-0105",
                language=Language.ENGLISH,
                order_id="ORD005",
                order_created=now - timedelta(hours=6),
                ai_called_before=False,
                due_by=now + timedelta(days=2),
            ),
            # Priority 4: Incomplete intake
            Patient(
                patient_id="PRE006",
                name="Sarah Brown",
                phone="555-0106",
                language=Language.ENGLISH,
                order_id="ORD006",
                order_created=now - timedelta(hours=3),
                intake_status=IntakeStatus.INCOMPLETE,
                ai_called_before=False,
                due_by=now + timedelta(days=2),
            ),
            # Priority 3: Chinese speaker
            Patient(
                patient_id="PRE007",
                name="Wei Zhang",
                phone="555-0107",
                language=Language.CHINESE,
                order_id="ORD007",
                order_created=now - timedelta(hours=18),
                has_called_in_before=True,
                ai_called_before=False,
                due_by=now + timedelta(days=1),
            ),
        ]

        for patient in sample_patients:
            self._patients[patient.patient_id] = patient

    def get_all_patients(self) -> list[Patient]:
        """Get all patients in the queue."""
        return list(self._patients.values())

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Get a specific patient by ID."""
        return self._patients.get(patient_id)

    def get_outbound_queue(self, max_attempts: int = 3, min_hours_between: int = 6) -> list[Patient]:
        """Get patients eligible for outbound calling, sorted by priority."""
        now = datetime.now()
        eligible = []

        for patient in self._patients.values():
            # Skip if max attempts reached
            if patient.attempt_count >= max_attempts:
                continue

            # Skip if called too recently
            if patient.last_attempt_at:
                hours_since_last = (now - patient.last_attempt_at).total_seconds() / 3600
                if hours_since_last < min_hours_between:
                    continue

            eligible.append(patient)

        # Sort by priority bucket, then due_by, then order_created, then attempt_count
        eligible.sort(
            key=lambda p: (
                p.priority_bucket,
                p.due_by or datetime.max,
                p.order_created or datetime.max,
                p.attempt_count,
            )
        )

        return eligible

    def get_next_candidate(self, max_attempts: int = 3, min_hours_between: int = 6) -> Optional[Patient]:
        """Get the next patient to call."""
        queue = self.get_outbound_queue(max_attempts, min_hours_between)
        return queue[0] if queue else None

    def update_patient_after_call(
        self,
        patient_id: str,
        outcome: str,
        increment_attempt: bool = True,
    ):
        """Update patient record after a call attempt."""
        patient = self._patients.get(patient_id)
        if patient:
            if increment_attempt:
                patient.attempt_count += 1
            patient.last_attempt_at = datetime.now()
            patient.last_outcome = outcome
            patient.ai_called_before = True
            # Recompute priority
            patient.priority_bucket = patient._compute_priority()

    def add_patient(self, patient: Patient):
        """Add a new patient to the queue."""
        self._patients[patient.patient_id] = patient

    def remove_patient(self, patient_id: str):
        """Remove a patient from the queue."""
        self._patients.pop(patient_id, None)

    def reset_to_sample_data(self):
        """Reset to initial sample data."""
        self._patients.clear()
        self._load_sample_data()


# Global instance
_patient_provider: Optional[MockPatientProvider] = None


def get_patient_provider() -> MockPatientProvider:
    """Get the global patient provider instance."""
    global _patient_provider
    if _patient_provider is None:
        _patient_provider = MockPatientProvider()
    return _patient_provider
