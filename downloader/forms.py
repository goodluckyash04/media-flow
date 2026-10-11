"""
Django forms for user input.
All forms validate their inputs before creating model instances.
"""

from pathlib import Path

from django import forms
from django.conf import settings

from downloader.models import AppSettings, AudioFormat
from downloader.utils.validators import (
    validate_audio_format,
    validate_audio_quality,
    validate_filename_template,
    validate_output_dir,
    validate_url,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_choices():
    return [(k, v) for k, v in settings.SUPPORTED_AUDIO_FORMATS.items()]


def _quality_choices():
    return [
        ("best", "Best available"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]


# ---------------------------------------------------------------------------
# Download form
# ---------------------------------------------------------------------------

class DownloadForm(forms.Form):
    url = forms.URLField(
        label="Media URL",
        max_length=2000,
        widget=forms.URLInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "https://www.youtube.com/watch?v=...",
                "autocomplete": "off",
                "id": "id_url",
            }
        ),
    )
    audio_only = forms.BooleanField(
        label="Audio only",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_audio_only"}),
    )
    output_format = forms.ChoiceField(
        label="Output format",
        choices=_format_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_output_format"}),
    )
    output_quality = forms.ChoiceField(
        label="Quality",
        choices=_quality_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_output_quality"}),
    )
    output_dir = forms.CharField(
        label="Output directory",
        required=False,
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Leave blank to use default",
                "id": "id_output_dir",
            }
        ),
    )
    inspect_only = forms.BooleanField(
        label="Inspect only (do not download)",
        required=False,
        initial=False,
        widget=forms.HiddenInput(),
    )

    def clean_url(self):
        return validate_url(self.cleaned_data["url"])

    def clean_output_format(self):
        return validate_audio_format(self.cleaned_data["output_format"])

    def clean_output_dir(self):
        raw = self.cleaned_data.get("output_dir", "").strip()
        if not raw:
            return ""
        return str(validate_output_dir(raw))

    def clean(self):
        cleaned = super().clean()
        fmt = cleaned.get("output_format")
        quality = cleaned.get("output_quality")
        if fmt and quality:
            try:
                validate_audio_quality(quality, fmt)
            except Exception as exc:
                self.add_error("output_quality", exc)
        return cleaned


# ---------------------------------------------------------------------------
# Playlist form
# ---------------------------------------------------------------------------

class PlaylistForm(forms.Form):
    url = forms.URLField(
        label="Playlist URL",
        max_length=2000,
        widget=forms.URLInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "https://www.youtube.com/playlist?list=...",
                "autocomplete": "off",
                "id": "id_pl_url",
            }
        ),
    )
    output_format = forms.ChoiceField(
        label="Output format",
        choices=_format_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_pl_format"}),
    )
    output_quality = forms.ChoiceField(
        label="Quality",
        choices=_quality_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_pl_quality"}),
    )
    output_dir = forms.CharField(
        label="Output directory",
        required=False,
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Leave blank to use default",
                "id": "id_pl_output_dir",
            }
        ),
    )

    def clean_url(self):
        return validate_url(self.cleaned_data["url"])

    def clean_output_format(self):
        return validate_audio_format(self.cleaned_data["output_format"])

    def clean_output_dir(self):
        raw = self.cleaned_data.get("output_dir", "").strip()
        if not raw:
            return ""
        return str(validate_output_dir(raw))


# ---------------------------------------------------------------------------
# Conversion form
# ---------------------------------------------------------------------------

class ConversionForm(forms.Form):
    input_files = forms.CharField(
        label="Input files",
        widget=forms.HiddenInput(attrs={"id": "id_input_files"}),
        help_text="JSON list of file paths selected via the file picker.",
    )
    output_format = forms.ChoiceField(
        label="Output format",
        choices=_format_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_conv_format"}),
    )
    output_quality = forms.ChoiceField(
        label="Quality",
        choices=_quality_choices,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_conv_quality"}),
    )
    output_dir = forms.CharField(
        label="Output directory",
        required=False,
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Leave blank to save alongside source file",
                "id": "id_conv_output_dir",
            }
        ),
    )

    def clean_output_format(self):
        return validate_audio_format(self.cleaned_data["output_format"])

    def clean_output_dir(self):
        raw = self.cleaned_data.get("output_dir", "").strip()
        if not raw:
            return ""
        return str(validate_output_dir(raw))

    def clean_input_files(self):
        import json

        raw = self.cleaned_data.get("input_files", "")
        try:
            files = json.loads(raw)
        except Exception:
            raise forms.ValidationError("Invalid file list format.")

        if not files or not isinstance(files, list):
            raise forms.ValidationError("At least one input file is required.")

        validated = []
        for p in files:
            path = Path(str(p).strip())
            if not path.exists():
                raise forms.ValidationError(f"File not found: {path}")
            if not path.is_file():
                raise forms.ValidationError(f"Not a file: {path}")
            validated.append(str(path))

        return validated


# ---------------------------------------------------------------------------
# Settings form
# ---------------------------------------------------------------------------

class SettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = [
            "download_dir",
            "filename_template",
            "max_concurrent_jobs",
            "default_audio_format",
            "default_audio_quality",
            "theme",
            "ffmpeg_path",
            "ffprobe_path",
            "spotify_client_id",
            "spotify_client_secret",
        ]
        widgets = {
            "download_dir": forms.TextInput(
                attrs={"class": "form-control", "id": "id_settings_download_dir"}
            ),
            "filename_template": forms.TextInput(
                attrs={"class": "form-control font-monospace", "id": "id_filename_template"}
            ),
            "max_concurrent_jobs": forms.NumberInput(
                attrs={"class": "form-control", "min": 1, "max": 10, "id": "id_max_concurrent"}
            ),
            "default_audio_format": forms.Select(
                attrs={"class": "form-select", "id": "id_default_format"}
            ),
            "default_audio_quality": forms.Select(
                choices=[
                    ("best", "Best"),
                    ("high", "High"),
                    ("medium", "Medium"),
                    ("low", "Low"),
                ],
                attrs={"class": "form-select", "id": "id_default_quality"},
            ),
            "theme": forms.Select(
                attrs={"class": "form-select", "id": "id_theme"}
            ),
            "ffmpeg_path": forms.TextInput(
                attrs={"class": "form-control font-monospace", "id": "id_ffmpeg_path"}
            ),
            "ffprobe_path": forms.TextInput(
                attrs={"class": "form-control font-monospace", "id": "id_ffprobe_path"}
            ),
            "spotify_client_id": forms.TextInput(
                attrs={"class": "form-control", "id": "id_spotify_client_id", "autocomplete": "off"}
            ),
            "spotify_client_secret": forms.PasswordInput(
                attrs={"class": "form-control", "id": "id_spotify_secret", "autocomplete": "off"},
                render_value=True,
            ),
        }

    def clean_filename_template(self):
        return validate_filename_template(self.cleaned_data["filename_template"])

    def clean_download_dir(self):
        raw = self.cleaned_data.get("download_dir", "").strip()
        if raw:
            validate_output_dir(raw)
        return raw
