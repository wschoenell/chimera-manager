from distutils.core import setup

setup(
    name='chimera_manager',
    version='0.0.1',
    packages=['chimera_manager', 'chimera_manager.controllers', 'chimera_manager.controllers.scheduler',
              'chimera_manager.core', 'chimera_manager.controllers.scheduler.algorithms'],
    scripts=['scripts/chimera-manager', 'scripts/chimera-robobs'],
    install_requires=['python-telegram-bot'],
    url='http://github.com/astroufsc/chimera-manager',
    license='GPL v2',
    author='Tiago Ribeiro',
    author_email='tribeiro@ufs.br',
    description='Observatory manager for chimera.'
)
