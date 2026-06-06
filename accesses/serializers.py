from rest_framework import serializers

from users.models import CustomUser, Membership

from .models import Access

# region AccessUser
class AccessUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "email", "nif_cif")

# region AccessMembership
class AccessMembershipSerializer(serializers.ModelSerializer):
    membership_type_name = serializers.CharField(source='membership_type.name', read_only=True)
    resource_name = serializers.CharField(source='resource.name', read_only=True)

    class Meta:
        model = Membership
        fields = ("membership_type_name", "resource_name", "end_date")

# region Access
class AccessSerializer(serializers.ModelSerializer):
    user = AccessUserSerializer(read_only=True)
    membership = AccessMembershipSerializer(read_only=True)

    class Meta:
        model = Access
        fields = (
            "id",
            "event",
            "type",
            "result",
            "user",
            "user_name",
            "user_email",
            "user_nif_cif",
            "membership",
        )
        extra_kwargs = {
            'id': {'read_only': True},
            'event': {'read_only': True},
            'user': {'read_only': True},
            'membership': {'read_only': True},
        }
