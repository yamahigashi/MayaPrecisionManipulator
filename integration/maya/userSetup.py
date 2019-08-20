# # -*- coding: utf-8 -*-
from textwrap import dedent
import maya.cmds as cmds


if __name__ == '__main__':
    cmds.evalDeferred(dedent(
        """
        import precisionmanipulator as pm
        pm.hook()
        """
    ))
