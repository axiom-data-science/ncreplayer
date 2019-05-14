## ncreplayer

[![Build Status](https://travis-ci.org/axiom-data-science/ncreplayer.svg?branch=master)](https://travis-ci.org/axiom-data-science/ncreplayer)
[![License](http://img.shields.io/:license-mit-blue.svg)](http://doge.mit-license.org)


Small little utility designed to load a CF DSG compliant netCDF file and replay it back onto a Kafka topic in either `batch` mode or `stream` mode. Optionally control the timestamps and timedeltas in the original file using configuration parameters.

Data is formatted as described in the AVRO schema file `schema.avsc`. You can choose to serialize the data as `avro`, `msgpack` or the default `json`.


## WHY?

This utility is designed to make my life easier. It isn't inteded to be used by many people but has been useful for:

*  Playing back data in a netCDF file with different times and intervals than what is defined in the file.
*  Setting up a quick stream of data for load testing.
*  Transitioning parts of large systems that rely on static files to stream processing.
*  Accepting a standardized data format from collaborators (netCDF/CF/DSG) and being able to stream it into larger systems.


## Data Format

**Simplest example**
```json
{
  "uid": "1",
  "time": "2019-04-01T00:00:00Z",
  "lat": 30.5,
  "lon": -76.5,
}
```

**Full Example**
```yaml
{
  "uid": "1",
  "gid": null,
  "time": "2019-04-01T00:00:00Z",
  "lat": 30.5,
  "lon": -76.5,
  "z": null,
  "values": {
    "salinity": 30.2,
    "temperature":  46.5
  },
  "meta": ""
}
```

*  `values` objects are optional and are a multi-type AVRO `map`.
*  `meta` is optional and open-ended. It is intended to carry along metadata to describe the `values`. I recommend using `nco-json`. This is useful if the system listening to these messages needs some context about the data, like streaming data to a website. YMMV.


## Configuration

This program uses [`Click`](https://click.palletsprojects.com/) for the CLI interface.  I probably spent 50% of the time making this utility just playing around with the CLI interface. I have no idea if what I came up with is mind-blowingly awesome or a bunch of crap. It works. Comments are welcome.

```sh
$ ncreplay
Usage: ncreplay [OPTIONS] FILENAME COMMAND [ARGS]...

Options:
  --brokers TEXT                 Kafka broker string (comman separated)
                                 [required]
  --topic TEXT                   Kafka topic to send the data to  [required]
  --packing [json|avro|msgpack]  The data packing algorithm to use
  --registry TEXT                URL to a Schema Registry if avro packing is
                                 requested
  --uid TEXT                     Variable name, global attribute, or value to
                                 use for the uid values
  --gid TEXT                     Variable name, global attribute, or value to
                                 use for the gid values
  --meta / --no-meta             Include the `nco-json` metadata in each
                                 message?
  --help                         Show this message and exit.

Commands:
  batch   Batch process a netCDF file in chunks, pausing every [chunk]...
  stream  Streams each unique timestep in the netCDF file every [delta]...
```

### batch

```sh
$ ncreplay /path/to/file.nc batch --help
Usage: ncreplay batch [OPTIONS]

  Batch process a netCDF file in chunks, pausing every [chunk] records
  for [delta] seconds. Optionally change the [starting] time of the file
  and/or change each timedelta using the [factor] and [offset] parameters.

Options:
  -s, --starting [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
  -f, --factor FLOAT
  -o, --offset FLOAT
  -d, --delta FLOAT
  -c, --chunk INTEGER
  --help                          Show this message and exit.
```

### stream

```sh
$ ncreplay /path/to/file.nc stream --help
Usage: ncreplay stream [OPTIONS]

  Streams each unqiue timestep in the netCDF file every [delta] seconds.
  Optionally you can control the [starting] point of the file and this will
  re-calculate all of the timestamps to match the original timedeltas.

Options:
  -s, --starting [%Y-%m-%d|%Y-%m-%dT%H:%M:%S|%Y-%m-%d %H:%M:%S]
  -d, --delta FLOAT
  --help                          Show this message and exit
```

## Development / Testing

There are no tests (yet) but you can play around with the options using files included in this repository

First setup a Kafka ecosystem

```bash
$ docker run -d --net=host \
    -e ZK_PORT=50000 \
    -e BROKER_PORT=4001 \
    -e REGISTRY_PORT=4002 \
    -e REST_PORT=4003 \
    -e CONNECT_PORT=4004 \
    -e WEB_PORT=4005 \
    -e RUNTESTS=0 \
    -e DISABLE=elastic,hbase \
    -e DISABLE_JMX=1 \
    -e RUNTESTS=0 \
    -e FORWARDLOGS=0 \
    -e SAMPLEDATA=0 \
    --name ncreplayer-testing \
  landoop/fast-data-dev:1.0.1
```

Then setup a listener

```bash
$ docker run -it --rm --net=host \
  landoop/fast-data-dev:1.0.1  \
    kafka-console-consumer \
      --bootstrap-server localhost:4001 \
      --topic axds-ncreplayer-data
```

Now batch or stream a file:

```bash
# Batch
$ ncreplay tests/data/gda_example.nc batch -d 10 -c 10

# Stream
$ ncreplay tests/data/gda_example.nc stream -d 10
```

To test the `avro` packing, setup a listener that will unpack the data automatically:

```bash
$ docker run -it --rm --net=host \
  landoop/fast-data-dev:1.0.1  \
    kafka-avro-console-consumer \
      --bootstrap-server localhost:4001 \
      --property schema.registry.url=http://localhost:4002 \
      --topic axds-ncreplayer-data
```

And use `avro` packing

```bash
$ ncreplay --packing avro tests/data/gda_example.nc batch -d 10 -c 10
```
