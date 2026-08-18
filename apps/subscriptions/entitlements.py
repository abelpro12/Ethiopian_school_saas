from apps.subscriptions.models import SchoolSubscription, SubscriptionStatus, PlanTier


class EntitlementService:
    """
    Centralized entitlement and feature flag service for SaaS plans.
    Avoids scattering `if plan == 'PREMIUM'` across views.
    """

    FEATURE_FLAGS = {
        'BASIC': {
            'FINANCE': True,
            'SMS': True,
            'TELEGRAM': False,
            'ADVANCED_REPORTS': False,
            'CUSTOM_BRANDING': False,
            'DOCUMENT_VAULT': True,
        },
        'STANDARD': {
            'FINANCE': True,
            'SMS': True,
            'TELEGRAM': True,
            'ADVANCED_REPORTS': True,
            'CUSTOM_BRANDING': False,
            'DOCUMENT_VAULT': True,
        },
        'PREMIUM': {
            'FINANCE': True,
            'SMS': True,
            'TELEGRAM': True,
            'ADVANCED_REPORTS': True,
            'CUSTOM_BRANDING': True,
            'DOCUMENT_VAULT': True,
        }
    }

    @classmethod
    def has_feature(cls, school, feature_name: str) -> bool:
        """
        Checks if a school subscription includes a specific feature flag.
        """
        if not school:
            return False

        try:
            sub = school.subscription
            if not sub.is_usable():
                return False

            tier = sub.plan.tier
            tier_features = cls.FEATURE_FLAGS.get(tier, cls.FEATURE_FLAGS['BASIC'])
            return tier_features.get(feature_name, False)
        except Exception:
            return False

    @classmethod
    def can_add_student(cls, school) -> bool:
        """
        Enforces subscription student quota limit.
        """
        try:
            sub = school.subscription
            meter = school.tenantusagemeter_objects.first()
            if not meter:
                return True
            return meter.current_students_count < sub.plan.max_students
        except Exception:
            return True

    @classmethod
    def can_add_teacher(cls, school) -> bool:
        """
        Enforces subscription teacher quota limit.
        """
        try:
            sub = school.subscription
            meter = school.tenantusagemeter_objects.first()
            if not meter:
                return True
            return meter.current_teachers_count < sub.plan.max_teachers
        except Exception:
            return True
