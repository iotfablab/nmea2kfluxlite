from setuptools import setup


def readme():
    with open('README.md') as f:
        return f.read()


setup(name='nmea2kfluxlite',
    version='0.0.1',
    description='CLI to parse Actisense-NGT1 NMEA2000 and publish them via MQTT and store into InfluxDB',
    long_description=readme(),
    author='Shan Desai',
    author_email='des@biba.uni-bremen.de',
    license='MIT',
    packages=['nmea2kfluxlite'],
    scripts=['bin/nmea2kfluxlite'],
    install_requires=[
        'paho-mqtt'
    ],
    include_data_package=True,
    zip_safe=False)
