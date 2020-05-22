# Generated by Django 2.2.4 on 2020-05-22 04:15

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mutations', '0022_mutation_mode'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mutation',
            name='ecoli_aapos',
        ),
        migrations.RemoveField(
            model_name='mutation',
            name='mrna_ntpos',
        ),
        migrations.RemoveField(
            model_name='mutation',
            name='predictor',
        ),
        migrations.AlterField(
            model_name='mutation',
            name='mode',
            field=models.CharField(blank=True, choices=[('SNP', 'Single Nucleotide Polymorphism'), ('LSP', 'Long String Polymorphism'), ('INS', 'Insertion'), ('DEL', 'Deletion')], db_index=True, default='SNP', max_length=4, null=True),
        ),
    ]
