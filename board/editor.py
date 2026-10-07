"""Small editorial workflow for the few jobs that need a human decision."""
from django import forms
from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .dedup import AGGREGATORS, official_duplicate
from .models import Job


class ReviewForm(forms.ModelForm):
    review_note = forms.CharField(
        label="Bilješka o provjeri", required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Navedite gdje ste potvrdili aktuelnost oglasa ili zašto ga odbacujete."}),
    )
    confirmed = forms.BooleanField(
        label="Provjerio/la sam originalni oglas, mjesto rada u BiH i da je oglas aktuelan.", required=False,
    )

    class Meta:
        model = Job
        fields = ("title", "city", "deadline", "source_published_at", "application_url", "location_evidence", "eligibility")
        labels = {
            "title": "Naziv pozicije", "city": "Grad", "deadline": "Rok za prijavu",
            "source_published_at": "Datum objave", "application_url": "Link za prijavu",
            "location_evidence": "Dokaz lokacije", "eligibility": "Uslovi prijave",
        }
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "source_published_at": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "location_evidence": forms.Textarea(attrs={"rows": 3}),
            "eligibility": forms.Textarea(attrs={"rows": 3}),
        }


@staff_member_required(login_url="/admin/login/")
@never_cache
def dashboard(request):
    official = list(Job.objects.exclude(source__adapter__in=AGGREGATORS).select_related("source__organization").defer("raw_text"))
    pending = [job for job in Job.objects.filter(status="review").select_related("source__organization").defer("raw_text").order_by("-first_seen_at", "-pk") if not official_duplicate(job, official)]
    recent = Job.objects.filter(status="published").select_related("source__organization").defer("raw_text").order_by("-published_at", "-pk")[:8]
    return render(request, "board/editor_list.html", {
        "pending": pending, "recent": recent,
        "published_count": Job.objects.filter(status="published").count(),
        "duplicate_count": Job.objects.filter(status="closed", closed_reason="duplicate").count(),
    })


@staff_member_required(login_url="/admin/login/")
@never_cache
def review_job(request, pk):
    job = get_object_or_404(Job.objects.select_related("source__organization"), pk=pk)
    if job.status != "review":
        raise Http404("Ovaj oglas više nije na provjeri")
    duplicate = official_duplicate(job)
    if request.method == "POST":
        decision = request.POST.get("decision")
        if decision not in ("save", "publish", "reject"):
            raise Http404("Nepoznata odluka")
        with transaction.atomic():
            job = Job.objects.select_for_update().select_related("source__organization").get(pk=pk)
            if job.status != "review" or job.content_hash != request.POST.get("content_hash"):
                messages.error(request, "Oglas se promijenio tokom provjere. Ponovo ga otvorite i pregledajte trenutnu verziju.")
                return redirect("editor_job", pk=pk)
            existing_duplicate = official_duplicate(job)
            form = ReviewForm(request.POST, instance=job)
            if form.is_valid():
                if decision == "publish":
                    if not form.cleaned_data["confirmed"]:
                        form.add_error("confirmed", "Potvrdite provjeru originalnog oglasa.")
                    if not form.cleaned_data["review_note"].strip():
                        form.add_error("review_note", "Upišite gdje ste potvrdili da je oglas aktuelan.")
                    if not job.source.enabled:
                        form.add_error(None, "Izvor je isključen. Oglas se ne može objaviti.")
                    if form.cleaned_data["deadline"] and form.cleaned_data["deadline"] < timezone.localdate():
                        form.add_error("deadline", "Rok je istekao. Oglas se ne može objaviti.")
                    if existing_duplicate or official_duplicate(form.instance):
                        form.add_error(None, "Oglas je već pronađen na službenom izvoru i ne treba ga ponovo objaviti.")
                elif decision == "reject" and not form.cleaned_data["review_note"].strip():
                    form.add_error("review_note", "Upišite razlog odbacivanja.")
                if not form.errors:
                    changed = set(form.changed_data) & set(form.Meta.fields)
                    job = form.save(commit=False)
                    job.manually_edited_fields = sorted(set(job.manually_edited_fields) | changed)
                    job.last_reviewed_at = timezone.now()
                    if decision == "publish":
                        job.status, job.closed_reason = "published", ""
                    elif decision == "reject":
                        job.status, job.closed_reason = "closed", "manual"
                    note = form.cleaned_data["review_note"].strip()
                    if note:
                        job.field_evidence = {**job.field_evidence, "editorial_note": note}
                    job.save()
                    LogEntry.objects.log_actions(request.user.pk, [job], CHANGE, change_message=f"Urednički pregled: {decision}. {note}"[:1000])
                    messages.success(request, {"save": "Izmjene su sačuvane.", "publish": "Oglas je objavljen.", "reject": "Oglas je odbačen."}[decision])
                    return redirect("editor_job", pk=pk) if decision == "save" else redirect("editor")
    else:
        form = ReviewForm(instance=job)
    return render(request, "board/editor_detail.html", {"job": job, "form": form, "duplicate": duplicate})
