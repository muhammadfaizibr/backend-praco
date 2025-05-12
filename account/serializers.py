from rest_framework import serializers
from account.models import User
from backend_praco.utils import send_email
from django.contrib.auth.hashers import check_password

class UserRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "company_name", "receive_marketing", "password"]
        extra_kwargs = {
            'password': {'write_only': True, 'min_length': 8, 'max_length': 20},
            'receive_marketing': {'required': False, 'allow_null': True}
        }

    def validate_email(self, value):
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=255, required=True)
    password = serializers.CharField(max_length=255, write_only=True, required=True)

    def validate_email(self, value):
        return value.lower()

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "company_name", "receive_marketing"]
        extra_kwargs = {
            'email': {'read_only': True},
            'id': {'read_only': True},
        }

    def get_fields(self):
        fields = super().get_fields()
        if self.context.get('request') and self.context['request'].method == 'PATCH':
            return {
                key: field for key, field in fields.items()
                if key in ['first_name', 'last_name', 'company_name', 'receive_marketing']
            }
        return fields

class EmailAuthenticationSerializer(serializers.Serializer):
    email = serializers.EmailField(
        max_length=255,
        required=True,
        error_messages={'required': 'Email address is required.', 'blank': 'Email address cannot be blank.'}
    )
    code = serializers.CharField(
        max_length=6,
        required=True,
        error_messages={'required': 'Verification code is required.', 'blank': 'Verification code cannot be blank.'}
    )
    authentication_type = serializers.ChoiceField(
        choices=['signup', 'forgot_password'],
        required=True,
        error_messages={'required': 'Authentication type is required.', 'invalid_choice': 'Invalid authentication type.'}
    )

    def validate(self, attrs):
        email = attrs.get('email').lower()
        code = attrs.get('code')
        authentication_type = attrs.get('authentication_type')

        # Check user existence
        user_exists = User.objects.filter(email=email).exists()
        attrs['exists'] = user_exists

        # Validate based on authentication type
        if authentication_type == 'signup' and user_exists:
            raise serializers.ValidationError("An account with this email already exists.")
        if authentication_type == 'forgot_password' and not user_exists:
            raise serializers.ValidationError("No account found with this email address.")

        # Create HTML content for the email
        html_body = f"""
        <html>
            <body>
                <h2>Your Verification Code</h2>
                <p>Your verification code is: <strong>{code}</strong></p>
                <p>Please use this code to complete your {'registration' if authentication_type == 'signup' else 'password reset'}.</p>
                <p>If you did not request this, please ignore this email.</p>
            </body>
        </html>
        """

        try:
            send_email(
                subject='Your OTP Code',
                body=html_body,
                receiver=email,
                is_html=True
            )
        except Exception as e:
            raise serializers.ValidationError(f"Failed to send OTP: {str(e)}")

        return attrs

class UserResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(
        max_length=255,
        required=True,
        error_messages={'required': 'Email address is required.', 'blank': 'Email address cannot be blank.'}
    )
    new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'New password is required.', 'blank': 'New password cannot be blank.'}
    )
    confirm_new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'Confirm password is required.', 'blank': 'Confirm password cannot be blank.'}
    )

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        email = attrs.get('email')
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')

        if new_password != confirm_new_password:
            raise serializers.ValidationError("New password and confirm password do not match.")

        user = User.objects.filter(email=email).first()
        if not user:
            raise serializers.ValidationError("No account found with this email address.")

        user.set_password(new_password)
        user.save()
        return attrs

class UserChangedPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        max_length=255,
        write_only=True,
        required=True,
        error_messages={'required': 'Current password is required.', 'blank': 'Current password cannot be blank.'}
    )
    new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'New password is required.', 'blank': 'New password cannot be blank.'}
    )
    confirm_new_password = serializers.CharField(
        max_length=20,
        min_length=8,
        write_only=True,
        required=True,
        error_messages={'required': 'Confirm password is required.', 'blank': 'Confirm password cannot be blank.'}
    )

    def validate(self, attrs):
        user = self.context.get('user')
        current_password = attrs.get('current_password')
        new_password = attrs.get('new_password')
        confirm_new_password = attrs.get('confirm_new_password')

        if not check_password(current_password, user.password):
            raise serializers.ValidationError("Current password is incorrect.")

        if new_password != confirm_new_password:
            raise serializers.ValidationError("New password and confirm password do not match.")

        if check_password(new_password, user.password):
            raise serializers.ValidationError("New password cannot be the same as the current password.")

        user.set_password(new_password)
        user.save()
        return attrs