from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Document, QAHistory


@receiver(pre_delete, sender=Document)
def remove_document_history(sender, instance, using, **kwargs):
    # Delete the complete answer if any of its source documents is removed.
    # pre_delete also runs for queryset deletes and cascading owner deletion.
    QAHistory.objects.using(using).filter(documents=instance).delete()
