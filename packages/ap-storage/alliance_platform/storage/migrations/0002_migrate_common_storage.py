from django.db import migrations


def copy_data_from_common_storage_table(apps, schema_editor):
    # Check if the old table exists
    sql = """
        DO $$ 
        BEGIN
            -- Check if the old table exists
            IF EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'common_storage_async_temp_file' 
                AND table_schema = 'public'
            ) THEN
                -- Copy data from the old table to the new one
                INSERT INTO alliance_platform_storage_async_temp_file (
                    created_at, original_filename, key, field_name, content_type_id, error, moved_to_location
                )
                SELECT 
                    created_at, original_filename, key, field_name, content_type_id, error, moved_to_location
                FROM common_storage_async_temp_file;
            END IF;
        END $$;
        """

    # Execute the SQL
    schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [
        ("alliance_platform_storage", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copy_data_from_common_storage_table),
    ]
