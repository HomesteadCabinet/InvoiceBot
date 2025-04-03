from rest_framework import serializers
from .models import DataRule, Vendor


class VendorSerializer(serializers.ModelSerializer):
    data_rules = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['id', 'name', 'invoice_type', 'data_rules']

    def get_data_rules(self, obj):
        from .serializers import DataRuleSerializer
        return DataRuleSerializer(obj.data_rules.all(), many=True).data


class DataRuleSerializer(serializers.ModelSerializer):
    vendor = VendorSerializer(read_only=True)

    class Meta:
        model = DataRule
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
