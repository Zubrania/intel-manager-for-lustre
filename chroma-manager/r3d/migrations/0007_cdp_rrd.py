# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding field 'CDP.row_id'
        db.add_column('r3d_cdp', 'row_id', self.gf('django.db.models.fields.BigIntegerField')(default=0), keep_default=False)

        # Adding field 'CDP.slot'
        db.add_column('r3d_cdp', 'slot', self.gf('django.db.models.fields.BigIntegerField')(default=0), keep_default=False)

        # Adding unique constraint on 'CDP', fields ['archive', 'datasource', 'slot']
        db.create_unique('r3d_cdp', ['archive_id', 'datasource_id', 'slot'])

        # For performance (InnoDB is optimized to make pk queries fast),
        # we'll drop the django-default pk and create our own.  This is
        # OK because we never access the CDP records via pk anyhow.
        if db.backend_name == "mysql":
            sql = """
ALTER TABLE r3d_cdp
CHANGE id id INT(11);
ALTER TABLE r3d_cdp
DROP PRIMARY KEY;
ALTER TABLE r3d_cdp
ADD PRIMARY KEY (row_id, archive_id, datasource_id);
            """
            db.execute(sql)


    def backwards(self, orm):

        # Go back to django defaults.
        if db.backend_name == "mysql":
            sql = """
ALTER TABLE r3d_cdp
DROP PRIMARY KEY;
ALTER TABLE r3d_cdp
ADD PRIMARY KEY (id);
ALTER TABLE r3d_cdp
CHANGE id id INT(11) AUTO_INCREMENT;
            """
            db.execute(sql)
        
        # Removing unique constraint on 'CDP', fields ['archive', 'datasource', 'slot']
        db.delete_unique('r3d_cdp', ['archive_id', 'datasource_id', 'slot'])

        # Deleting field 'CDP.row_id'
        db.delete_column('r3d_cdp', 'row_id')

        # Deleting field 'CDP.slot'
        db.delete_column('r3d_cdp', 'slot')


    models = {
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'r3d.archive': {
            'Meta': {'object_name': 'Archive'},
            'cdp_per_row': ('django.db.models.fields.BigIntegerField', [], {}),
            'cls': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'current_row': ('django.db.models.fields.BigIntegerField', [], {'default': '0'}),
            'database': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'archives'", 'to': "orm['r3d.Database']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'mod': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'rows': ('django.db.models.fields.BigIntegerField', [], {}),
            'xff': ('r3d.models.SciFloatField', [], {'default': '0.5'})
        },
        'r3d.cdp': {
            'Meta': {'unique_together': "(['archive', 'datasource', 'slot'],)", 'object_name': 'CDP'},
            'archive': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'cdps'", 'to': "orm['r3d.Archive']"}),
            'datasource': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'cdps'", 'to': "orm['r3d.Datasource']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'row_id': ('django.db.models.fields.BigIntegerField', [], {'default': '0'}),
            'slot': ('django.db.models.fields.BigIntegerField', [], {'default': '0'}),
            'value': ('r3d.models.SciFloatField', [], {'null': 'True'})
        },
        'r3d.database': {
            'Meta': {'unique_together': "(('content_type', 'object_id'),)", 'object_name': 'Database'},
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']", 'null': 'True'}),
            'ds_pickle': ('r3d.models.PickledObjectField', [], {'null': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'last_update': ('django.db.models.fields.BigIntegerField', [], {'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '255'}),
            'object_id': ('django.db.models.fields.PositiveIntegerField', [], {'null': 'True'}),
            'prep_pickle': ('r3d.models.PickledObjectField', [], {'null': 'True'}),
            'start': ('django.db.models.fields.BigIntegerField', [], {'default': '1334534143'}),
            'step': ('django.db.models.fields.BigIntegerField', [], {'default': '300'})
        },
        'r3d.datasource': {
            'Meta': {'unique_together': "(('database', 'name'),)", 'object_name': 'Datasource'},
            'cls': ('django.db.models.fields.CharField', [], {'max_length': '30'}),
            'database': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'datasources'", 'to': "orm['r3d.Database']"}),
            'heartbeat': ('django.db.models.fields.BigIntegerField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'max_reading': ('r3d.models.SciFloatField', [], {'null': 'True', 'blank': 'True'}),
            'min_reading': ('r3d.models.SciFloatField', [], {'null': 'True', 'blank': 'True'}),
            'mod': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '255'})
        }
    }

    complete_apps = ['r3d']
