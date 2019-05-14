#!python
# coding=utf-8
import time
import json
from pathlib import Path
from collections import OrderedDict
from datetime import timedelta, datetime

import click
import msgpack
import numpy as np
import pandas as pd
from avro.schema import Parse
from easyavro import EasyAvroProducer, EasyProducer
from pocean.dsg import *  # noqa
from pocean.cf import CFDataset
from pocean.utils import get_mapped_axes_variables, get_default_axes


import logging
L = logging.getLogger('easyavro')
L.addHandler(logging.StreamHandler())
L.setLevel(logging.INFO)


def extract_axes(filename):
    # Extract the correct axes based on file variables
    with CFDataset(filename) as ncd:
        axes_vars = get_mapped_axes_variables(ncd)._asdict()
        axes_names = { k: v.name for k, v in axes_vars.items() if v is not None }
        return get_default_axes(axes_names)


def extract_ncmeta(filename):
    # Extract the correct axes based on file variables
    with CFDataset(filename) as ncd:

        ncmeta = dict(ncd.meta())

        del ncmeta['dimensions']

        # limit variable attributes
        keep_var_attrs    = ['standard_name', 'units', 'long_name']
        vs = ncmeta.get('variables', OrderedDict())
        for k, v in vs.copy().items():
            for atname in v.get('attributes', {}).copy().keys():
                if atname not in keep_var_attrs:
                    del ncmeta['variables'][k]['attributes'][atname]

        # limit global attributes
        keep_global_attrs = ['id', 'naming_authority', 'project', 'uuid']
        ga = ncmeta.get('attributes', OrderedDict())
        for ganame in ga.copy().keys():
            if ganame not in keep_global_attrs:
                del ncmeta['attributes'][ganame]

        return ncmeta


def load(filename, axes, promotions):
    # Load the DSG and convert to a dataframe
    with CFDataset.load(filename) as ncd:

        df = ncd.to_dataframe(axes=axes)

        for toz, (fromz, extract_fromz) in promotions.items():

            if fromz and fromz in df.columns:
                # Are we a data variable?
                df[toz] = df[fromz]
            elif fromz and hasattr(ncd, fromz):
                # Are we a global attribute?
                df[toz] = getattr(ncd, fromz)
            elif fromz and isinstance(fromz, str):
                # Are we a passed in value?
                df[toz] = fromz
            elif extract_fromz:
                # Use the pass in defaults ordered by precedence
                for e in extract_fromz:
                    if e in df:
                        # Use the trajectory
                        df[toz] = df[e]
                        break

            if toz not in df:
                # Use nothing
                df[toz] = None

        return df


def recalc_with_factor_offset(df, axes, starting, factor, offset):

    df = df.sort_values(axes.t)

    # Calculate timediff before setting initial starting time
    timediff = df[axes.t] - df[axes.t].iloc[0]

    # If starting is defined, replace the initial time with a new initial time
    if starting is None:
        starting = df[axes.t].iloc[0]

    # Get seconds to apply factor and offset
    timediff = timediff.dt.total_seconds()
    timediff = timediff * factor
    timediff = timediff + offset

    newtimes = timediff.apply(lambda x: starting + timedelta(seconds=float(x)))
    df[axes.t] = newtimes

    return df


def recalc_with_delta(df, axes, starting, delta):
    """ Play back data with each timestep statically configured to be
        on the delta steps
    """
    df = df.sort_values(axes.t)

    # Calculate timediff before setting initial starting time
    timediff = df[axes.t] - df[axes.t].iloc[0]

    # One based standardized deltas (as 1 second intervals), then subtract
    # 1 to get zero based intervals
    zero_diffs = np.digitize(
        timediff.dt.total_seconds(), sorted(timediff.dt.total_seconds().unique())
    ) - 1

    # Get the real time by multiplying by the requested delta
    newtimes = pd.Series(zero_diffs).apply(
        lambda x: starting + timedelta(seconds=(delta * x))
    )
    df[axes.t] = newtimes

    return df


def send_frame(df, axes, producer, ncmeta, packing):
    records = []
    value_skips = [ 'Index', 'uid', 'gid' ]

    for row in df.itertuples():

        rowd = row._asdict()

        data = {
            "uid": rowd['uid'],
            "gid": rowd['gid'],
            "time": rowd[axes.t].isoformat(),
            "lat": rowd[axes.y],
            "lon": rowd[axes.x],
            "z": rowd[axes.z] or None,
            "values": {
                k: v for k, v in rowd.items() if k not in axes and k not in value_skips
            }
        }

        if ncmeta:
            data["meta"] = json.dumps(ncmeta)

        if packing is not None:
            data = packing(data)

        # Clear None values from data
        records.append((None, data))

    producer.produce(records)


@click.group()
@click.argument('filename', type=click.Path(exists=True))
@click.option('--brokers',  type=str, required=True, default='localhost:4001', help="Kafka broker string (comman separated)")
@click.option('--topic',    type=str, required=True, default='axds-netcdf-replayer-data', help="Kafka topic to send the data to")
@click.option('--packing',  type=click.Choice(['json', 'avro', 'msgpack']), default='json', help="The data packing algorithm to use")
@click.option('--registry', type=str, default='http://localhost:4002', help="URL to a Schema Registry if avro packing is requested")
@click.option('--uid', type=str, default='', help="Variable name, global attribute, or value to use for the uid values")
@click.option('--gid', type=str, default='', help="Variable name, global attribute, or value to use for the gid values")
@click.option('--meta/--no-meta', default=False, help="Include the `nco-json` metadata in each message?")
@click.pass_context
def setup(ctx, filename, brokers, topic, packing, registry, uid, gid, meta):
    # Learn about the axes from the netCDF file
    axes = extract_axes(filename)

    # Learn about the meta from the netCDF file if we should include it with the message
    if meta:
        ncmeta = extract_ncmeta(filename)
    else:
        ncmeta = None

    # Get a dataframe
    promotions = {
        'uid': (uid, (axes.trajectory, axes.station)),
        'gid': (gid, None)
    }
    df = load(filename, axes, promotions)

    # Store info in the context
    ctx.ensure_object(dict)
    ctx.obj['axes'] = axes
    ctx.obj['df'] = df
    ctx.obj['ncmeta'] = ncmeta

    # Setup the kafka producer
    if packing == 'avro':
        ctx.obj['packing'] = None
        schema_path = Path(__file__).parent.parent / 'schema.avsc'
        schema = Parse(schema_path.open('rb').read())
        bp = EasyAvroProducer(
            schema_registry_url=registry,
            kafka_brokers=brokers.split(','),
            kafka_topic=topic,
            value_schema=schema,
            key_schema='key'
        )
    elif packing == 'msgpack':
        ctx.obj['packing'] = lambda x: msgpack.packb(x, use_bin_type=True)
        bp = EasyProducer(
            kafka_brokers=brokers.split(','),
            kafka_topic=topic,
        )
    elif packing == 'json':
        ctx.obj['packing'] = json.dumps
        bp = EasyProducer(
            kafka_brokers=brokers.split(','),
            kafka_topic=topic,
        )

    ctx.obj['producer'] = bp


@setup.command()
@click.option('-s', '--starting', type=click.DateTime(), default=None)
@click.option('-f', '--factor',   type=click.FLOAT,      default=1.0)
@click.option('-o', '--offset',   type=click.FLOAT,      default=0.0)
@click.option('-d', '--delta',    type=click.FLOAT,      default=60.0)
@click.option('-c', '--chunk',    type=click.INT,        default=100)
@click.pass_context
def batch(ctx, starting, factor, offset, chunk, delta):
    """ Batch process a netCDF file in chunks, pausing every [chunk] records for [delta] seconds.
        Optionally change the [starting] time of the file and/or change each timedelta using the
        [factor] and [offset] parameters.
    """
    df = recalc_with_factor_offset(ctx.obj['df'], ctx.obj['axes'], starting, factor, offset)

    click.echo(f"{len(df)} rows total")

    while True:

        sub = df.iloc[0:chunk]
        click.echo(f"Sending {len(sub)} rows from {sub.time.min()} to {sub.time.max()}")
        send_frame(sub, ctx.obj['axes'], ctx.obj['producer'], ctx.obj['ncmeta'], ctx.obj['packing'])

        # reset df to be without the rows we just sent
        df = df.iloc[chunk:]
        if df.empty:
            break

        # Sleep for some time relative to delta
        click.echo(f"Sleeping for {delta} second(s)")
        time.sleep(delta)


@setup.command()
@click.option('-s', '--starting', type=click.DateTime(), default=datetime.utcnow().isoformat(timespec='seconds'))
@click.option('-d', '--delta',    type=click.FLOAT,      default=60.0)
@click.pass_context
def stream(ctx, starting, delta):
    """ Streams each unique timestep in the netCDF file every [delta] seconds.
        Optionally you can control the [starting] point of the file and this will re-calculate
        all of the timestamps to match the original timedeltas.
    """
    df = recalc_with_delta(ctx.obj['df'], ctx.obj['axes'], starting, delta)

    send_start = df.time.min()
    send_end = send_start + timedelta(seconds=delta)

    while True:

        sub_query = (df.time < send_end) & (df.time >= send_start)

        sub = df.loc[sub_query]  # Extract the rows to send
        click.echo(f"Sending {len(sub)} rows from {send_start} to {send_end}")
        send_frame(sub, ctx.obj['axes'], ctx.obj['producer'], ctx.obj['ncmeta'], ctx.obj['packing'])

        # reset df to be without the rows we just sent
        df = df.loc[~sub_query]
        if df.empty:
            break

        send_start = send_end
        send_end = send_start + timedelta(seconds=delta)

        # Sleep for some time relative to delta
        click.echo(f"Sleeping for {delta} second(s)")
        time.sleep(delta)


if __name__ == '__main__':
    setup()
