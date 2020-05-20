import os
from setuptools import setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='unbounded-thread-pool',
    version='0.2.0',
    packages=['unbounded_thread_pool'],
    license='MIT',
    description='ThreadPool with unlimited workers count.',
    long_description=README,
    long_description_content_type="text/markdown",
    author='romasku',
    author_email='romasku135@gmail.com',
    url='https://github.com/romasku/unbounded-thread-pool',
    python_requires=">=3.6",
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
)