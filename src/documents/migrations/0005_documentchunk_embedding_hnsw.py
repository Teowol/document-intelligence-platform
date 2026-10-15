from django.db import migrations

INDEX_NAME = "document_chunk_embedding_cosine_hnsw_idx"
TABLE = "documents_documentchunk"


class Migration(migrations.Migration):
    """Phase 6: HNSW index (cosine) for fast approximate semantic search."""

    dependencies = [
        ("documents", "0004_chunk_document_not_null"),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"""
            CREATE INDEX IF NOT EXISTS {INDEX_NAME}
            ON {TABLE} USING hnsw ("embedding" vector_cosine_ops);
            """,
            reverse_sql=f"""
            DROP INDEX IF EXISTS {INDEX_NAME};
            """,
        ),
    ]
