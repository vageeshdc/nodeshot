# signals
from django.db.models.signals import post_delete, post_save
from django.utils.translation import ugettext_lazy as _
from nodeshot.models import *
from settings import DEBUG, STATIC_GENERATOR, WEB_ROOT
from datetime import datetime, timedelta

# IS_SCRIPT is defined in management scripts to avoid sending notifications
try:
    IS_SCRIPT
except:
    IS_SCRIPT = False

def notify_on_delete(sender, instance, using, **kwargs):
    """
    Notify admins when nodes are deleted.
    Only for production use.
    """

    # if in testing mode or using an import script don't send emails
    if DEBUG or IS_SCRIPT:
        return False

    # if purging old unconfirmed nodes don't send emails
    if instance.status == 'u' and instance.added + timedelta(days=ACTIVATION_DAYS) < datetime.now():
        return False

    # prepare context
    context = {
        'node': instance,
        'site': SITE
    }

    # notify admins that want to receive notifications
    notify_admins(instance, _('Node deleted on %s') % SITE.get('name'), 'email_notifications/node-deleted-admin.txt', context, skip=False)

if not IS_SCRIPT:
    post_delete.connect(notify_on_delete, sender=Node)

from utils import distance
from django.db.models import Q, Count

def update_statistics():
    """
    Adds a new record in the statistic table if needed. Called by signals
    """

    # retrieve links, select_related() reduces the number of queries, only() selects only the fields we need
    links = Link.objects.all().select_related().only(
        'from_interface__device__node__lat', 'from_interface__device__node__lng',
        'to_interface__device__node__lat', 'to_interface__device__node__lng'
    )

    # get counts of the active nodes, potential nodes, hotspots and group the results
    # Count() is a function provided by django.db.models
    nodes = Node.objects.values('status').annotate(count=Count('status')).filter(Q(status='a') | Q(status='ah') | Q(status='h') | Q(status='p')).order_by('status')
    # evaluate queryset to avoid repeating the same query
    nodes = list(nodes)

    # active & hotspot
    active_and_hotspots = nodes[1].get('count')
    # active nodes
    active_nodes = nodes[0].get('count') + active_and_hotspots
    # hotspots
    hotspots = nodes[2].get('count') + active_and_hotspots
    # potential nodes
    potential_nodes = nodes[3].get('count')
    # number of links
    link_count = Link.objects.count()

    # calculate total km of the links
    km = 0
    for l in links:
        km += distance((l.from_interface.device.node.lat,l.from_interface.device.node.lng), (l.to_interface.device.node.lat, l.to_interface.device.node.lng))
    km = '%0.3f' % km

    # retrieve last statistic
    try:
        last = Statistic.objects.all().order_by('-pk')[0]
    # no statistics in the database yet
    except IndexError:
        last = False

    # compare last statistic with data we have now (km are converted to string in order to avoid django to mess the comparation caused by float field)
    if last and last.active_nodes == active_nodes and last.hotspots == hotspots and last.potential_nodes == potential_nodes and last.links == link_count and str(last.km) == str(km):
        # if data is the same there's no need to add a new record
        return False
    else:
        # if we got different numbers it means something has changed and we need to insert a new record in the statistics
        new = Statistic(active_nodes=active_nodes, potential_nodes=potential_nodes, hotspots=hotspots, links=link_count, km=km)
        new.save()

if not IS_SCRIPT:
    def update_statistics_signal(sender, instance, using, **kwargs):
        """
        Signal for update_satistics()
        """
        update_statistics()
    # signals to update statistics every time something is modified or deleted
    post_delete.connect(update_statistics_signal, sender=Node)
    post_delete.connect(update_statistics_signal, sender=Link)
    post_save.connect(update_statistics_signal, sender=Node)
    post_save.connect(update_statistics_signal, sender=Link)

if STATIC_GENERATOR:
    from staticgenerator import quick_delete
    import shutil

    def clear_cache():
        """
        Clears the cache, might be used also by scripts like snmp.py (in nodeshot/scripts/)
        This function can be used also outside of signals
        """
        quick_delete('/')
        quick_delete('nodes.json')
        quick_delete('jstree.json')
        quick_delete('nodes.kml')
        quick_delete('overview/')
        quick_delete('tab3/')
        quick_delete('tab4/')
        try:
            shutil.rmtree('%s/select/' % WEB_ROOT)
        except OSError:
            pass
        try:
            shutil.rmtree('%s/node/' % WEB_ROOT)
        except OSError:
            pass
        try:
            shutil.rmtree('%s/search/' % WEB_ROOT)
        except OSError:
            pass

    if not IS_SCRIPT:
        def clear_cache_signal(sender, instance, using, **kwargs):
            """ Signal for clear_cache() """
            clear_cache()
    
        post_delete.connect(clear_cache_signal, sender=Node)
        post_save.connect(clear_cache_signal, sender=Node)
        post_delete.connect(clear_cache_signal, sender=Link)
        post_save.connect(clear_cache_signal, sender=Link)
        post_delete.connect(clear_cache_signal, sender=Device)
        post_save.connect(clear_cache_signal, sender=Device)
        post_save.connect(clear_cache_signal, sender=Interface)
        post_delete.connect(clear_cache_signal, sender=Interface)