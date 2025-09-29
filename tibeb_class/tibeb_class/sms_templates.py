class SMSTemplateHelper:
    """
    Helper class to generate SMS messages for different flows.
    """

    @staticmethod
    def verification_otp(otp: str) -> str:
        return f"Your OTP code is {otp} for tibebclass verification. It is valid for 20 minutes."

    @staticmethod
    def password_reset_otp(otp: str) -> str:
        return f"Your OTP code is {otp} to reset your tibebclass account password. It is valid for 20 minutes."
    @staticmethod
    def change_username_otp(otp: str) -> str:
        return f"Your OTP code is {otp} to change your tibebclass account username. It is valid for 20 minutes."
