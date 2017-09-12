from setuptools import setup

version = '1.0.0'

package_dir = 'logutil'

setup(name='logutil',

    version=version,

    description='rotate logfile in specify time.',

    packages=[package_dir, ],
)
