from django import forms

from .models import Contract, Performance
from dal import autocomplete

class PerformanceContractForm(forms.Form):
    contract = forms.ModelChoiceField(
        queryset=Contract.objects.all(),
        widget=autocomplete.ModelSelect2(url="contract-autocomplete"),
    )

class LeaveDatePrefillForm(forms.Form):
    from_date = forms.DateField(required=True, widget=forms.DateInput(attrs=dict(type='date')))
    to_date = forms.DateField(required=True, widget=forms.DateInput(attrs=dict(type='date')))
    
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("user")
        super(LeaveDatePrefillForm, self).__init__(*args, **kwargs)