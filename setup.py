from distutils.core import setup

setup(
    name='chimera_manager',
    version='0.0.1',
    packages=['chimera_manager', 'chimera_manager.controllers','chimera_manager.core','chimera_manager.gui'],
    package_data={'chimera_manager.gui': ['main_manager.ui']},
    include_package_data=True,
    scripts=['scripts/chimera-manager'],
    url='http://github.com/astroufsc/chimera-manager',
    license='GPL v2',
    author='Tiago Ribeiro',
    author_email='tribeiro@ufs.br',
    description='Observatory manager for chimera.'
)
