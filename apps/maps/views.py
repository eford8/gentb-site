#
# Copyright (C) 2017  Dr. Maha Farhat
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Views for the mapping application
"""

from __future__ import print_function

import json
from collections import defaultdict, OrderedDict
from django.views.generic import TemplateView
from django.db.models import Count, Q, F, IntegerField
from django.db.models.functions import Cast

from apps.mutations.models import (
    ImportSource, StrainSource, Mutation, GeneLocus, Genome,
    RESISTANCE, RESISTANCE_GROUP,
    Paper, BioProject
)

from .mixins import JsonView, DataSlicerMixin
from .utils import GraphData
from .models import Country

LINEAGE_COLS = ['spoligotype_family', 'rflp_family', 'principle_group', 'wgs_group']
LINEAGE_NAMES = ['Spoligo', 'RFLP', 'PGG', 'WGS']

class MapPage(TemplateView):
    """The html map page everything is provided by javascript"""
    title = "Mutations Map"
    template_name = 'maps/map.html'


class Sources(JsonView, DataSlicerMixin):
    """
    Provide a json output that slices source import data
    """
    model = ImportSource
    order = ['pk']

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        return {'values': list(self.get_sources())}

    def get_sources(self):
        """Return a list of data sources"""
        if self.request.GET.get('fields', '') == 'bio':
            for bioproject in BioProject.objects.filter(strains__isnull=False):
                yield dict(kind='bioproject', pk=bioproject.pk, name=bioproject.name,
                           count=bioproject.strains.count())
        else:
            for source in self.get_data():
                yield dict(kind='source', pk=source.pk, name=source.name,
                           uploader=str(source.uploader), count=source.strainsource_set.count())
            for paper in Paper.objects.filter(strains__isnull=False):
                yield dict(kind='paper', pk=paper.pk, name=paper.name,
                           url=paper.url, count=paper.strains.count())


class Places(JsonView, DataSlicerMixin):
    """
    Provide a json output that slices mutation data by country
    """
    model = StrainSource
    order = ['country__name', 'country__region']
    values = ['country__iso2', 'resistance_group']
    filters = dict(
        [
            ('source', 'importer'),
            ('paper', 'source_paper'),
            ('drug', 'drugs__drug__code'),
        ] + zip(LINEAGE_NAMES, LINEAGE_COLS)
    )

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        ret = defaultdict(lambda: defaultdict(int))
        for row in self.get_data().annotate(count=Count('pk')):
            group = row['resistance_group']
            if group == 'S':
                group = 'Sensitive'
            if group is not None:
                ret[row['country__iso2']][group] = row['count']
                ret[row['country__iso2']]['Total'] += row['count']

        return {
            "type": "FeatureCollection",
            'features': [
                {
                    # Turning this to json and then back to python just to feed
                    # to JsonView, seems a little wasteful and redundent.
                    "geometry": json.loads(country.geom.geojson),
                    "popupContent": country.name,
                    "type": "Feature",
                    "id": country.id,
                    "properties": {
                        "name": country.name,
                        "value": country.iso2,
                        "values": ret[country.iso2],
                    },
                } for country in Country.objects.filter(iso2__in=list(ret))
            ],
        }


class DrugList(JsonView, DataSlicerMixin):
    """Provide a json data slice into the drug resistance data"""
    model = StrainSource
    order = ['drugs__drug__regimen', 'drugs__drug__order',]
    values = ['drugs__drug__name', 'drugs__drug__code', 'drugs__resistance']
    filters = dict(
        [
            ('map', 'country__iso2'),
            ('source', 'importer'),
            ('paper', 'source_paper'),
        ] + zip(LINEAGE_NAMES, LINEAGE_COLS)
    )

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        return {
            'data': GraphData(
                self.get_data().annotate(count=Count('pk')),
                'drugs__drug__code', 'count', 'drugs__resistance',
            ).set_axis('z', RESISTANCE).to_graph(),
        }


class Lineages(JsonView, DataSlicerMixin):
    """Provide a json data slice into the Lineages data"""
    model = StrainSource
    order = ['spoligotype_family']
    values = LINEAGE_COLS
    filters = {
        'map': 'country__iso2',
        'drug': 'drugs__drug__code',
    }

    def get_queryset(self, without=None):
        _qs = super(Lineages, self).get_queryset()
        return _qs.filter(spoligotype_family__isnull=False)

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        return {
            'data': GraphData(
                self.get_data().annotate(count=Count('pk')),
                self.values, 'count', None, trim=True)
                    .set_axis('z', zip(self.values, LINEAGE_NAMES))
                    .set_axis('x', [(None, "Not Available")])
                    .to_graph()
        }


class LocusRange(JsonView, DataSlicerMixin):
    """Lookup locuses and return mutations blocked into buckets"""
    model = Mutation
    filters = {
        'drug': 'strain_mutations__strain__drugs__drug__code',
        'map': 'strain_mutations__strain__country__iso2',
        'src': 'strain_mutations__strain__importer',
    }
    def get_context_data(self, **_):
        """Returns the list of mutations blocked into ranges for this gene"""
        return dict(self.get_gene_range(**self.request.GET))

    def get_gene_range(self, locus, synonymous=False, **_):
        """Returns a list of segments in a gene, as a dict-generator"""
        genome = Genome.objects.get(code='H37Rv')
        mutations = self.get_queryset().filter(nucleotide_position__isnull=False)
        try:
            locus = GeneLocus.objects.get(name=locus[0])
            mutations = mutations.filter(gene_locus=locus)
            count = mutations.count()
            start = locus.start
            end = locus.stop
            yield 'title', "{0.name} / {0.previous_id} ({1} mutations)".format(locus, count)
        except GeneLocus.DoesNotExist:
            # All mutations in the whole genome
            count = mutations.count()
            start = 0
            end = int(genome.length)
            yield 'title', "{0.code} ({1} mutations)".format(genome, count)

        yield 'start', start
        yield 'end', end
        if synonymous in (False, 0, 'false'):
            mutations = mutations.exclude(syn='S')

        yield 'count', count
        values = defaultdict(list)
        girth = (end - start) / 50
        for name, pos in self.get_list(mutations, 'name', 'nucleotide_position'):
            bucket = int((pos - start) / (girth or 1))
            values[bucket].append(name)
        yield 'values', values
        yield 'max', max([len(i) for i in values.values()] + [0])


class LocusList(JsonView, DataSlicerMixin):
    """Get a list of locuses that somewhat match the given locus string"""
    model = Mutation

    def get_context_data(self, **_):
        """Return a list of locuses with this name"""
        locus = self.request.GET['locus']
        qset = GeneLocus.objects.filter(
            Q(name__istartswith=locus)
            | Q(previous_id__istartswith=locus)
            | Q(gene_symbol__istartswith=locus),
        )
        return {
            'msg': "Found %d genes" % qset.count(),
            'values': self.get_list(qset, 'name')
        }


class Mutations(JsonView, DataSlicerMixin):
    """Provide a lookup into the mutations database for selecting anavailable mutation"""
    model = Mutation
    values = ['pk']
    filters = {
        'snp': 'name__icontains',
        'ecoli': 'ecoli_aapos',
        'locus': 'gene_locus__name',
        'drug': 'strain_mutations__strain__drugs__drug__code',
        'map': 'strain_mutations__strain__country__iso2',
        'src': 'strain_mutations__strain__importer',
    }

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        if 'snp' not in self.request.GET and 'ecoli' not in self.request.GET:
            return {'values': []}

        # Otherwise mutation query
        qset = self.get_data()
        if qset.count() == 0:
            return {'msg': 'None found'}
        elif qset.count() > 200:
            return {'msg': 'Too many (%d)' % qset.count()}

        return {
            'msg': "Found %d mutations" % qset.count(),
            'values': list(self.get_my_list(qset)),
        }

    def get_my_list(self, _qs):
        """The core get list for thsi json data"""
        for (name, aar, eaa, aav) in self.get_list(
                _qs, 'name', 'aminoacid_reference', 'ecoli_aapos', 'aminoacid_varient'):
            if 'ecoli' in self.request.GET:
                yield {
                    'name': "%s+%s%s%s (E:%s)" % (name, aar, eaa, aav, eaa),
                    'value': name,
                }
            else:
                yield name



class MutationView(JsonView, DataSlicerMixin):
    """Provide a way to look at the resistance data via selected mutations"""
    model = StrainSource
    required = ['mutation[]',]
    filters = {
        'mutation[]': 'mutations__mutation__name__in',
        'drug': 'drugs__drug__code',
        'map': 'country__iso2',
        'src': 'importer',
    }
    @property
    def values(self):
        """Return drug or resistance values depending on the GET mode"""
        if 'drug' in self.request.GET:
            return ['mutations__mutation__name', 'drugs__resistance']
        return ['mutations__mutation__name', 'resistance_group']

    @property
    def categories(self):
        """Return the categories available depending on the GET mode"""
        if 'drug' in self.request.GET:
            return OrderedDict(RESISTANCE)
        return OrderedDict(RESISTANCE_GROUP)

    def get_context_data(self, **_):
        """Return a dictionary of template variables"""
        mutations = self.request.GET.getlist(self.required[0])
        totals = self.get_data(without=self.values[0]).annotate(count=Count('pk'))
        totals = [(row[self.values[1]], row['count']) for row in totals]
        _qs = self.get_data().annotate(count=Count('pk'))
        return {
            'data': GraphData(_qs, self.values[0], 'count', self.values[-1])
                    .set_axis('z', self.categories, trim=True)
                    .set_axis('x', mutations)
                    .set_axis('y', totals, trim=[None])
                    .to_graph()
            }
