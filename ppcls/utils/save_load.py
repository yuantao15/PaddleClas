# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserve.
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an "AS IS" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import errno
import os
import shutil
import tempfile

import paddle
import paddle.fluid as fluid

from ppcls.utils import logger

__all__ = ['init_model', 'save_model']


def _mkdir_if_not_exist(path):
    """
    mkdir if not exists, ignore the exception when multiprocess mkdir together
    """
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(path):
                logger.warning(
                    'be happy if some process has already created {}'.format(
                        path))
            else:
                raise OSError('Failed to mkdir {}'.format(path))


def _load_state(path):
    if os.path.exists(path + '.pdopt'):
        # XXX another hack to ignore the optimizer state
        tmp = tempfile.mkdtemp()
        dst = os.path.join(tmp, os.path.basename(os.path.normpath(path)))
        shutil.copy(path + '.pdparams', dst + '.pdparams')
        state = fluid.io.load_program_state(dst)
        shutil.rmtree(tmp)
    else:
        state = fluid.io.load_program_state(path)
    return state


def load_params(exe, prog, path, ignore_params=[]):
    """
    Load model from the given path.
    Args:
        exe (fluid.Executor): The fluid.Executor object.
        prog (fluid.Program): load weight to which Program object.
        path (string): URL string or loca model path.
        ignore_params (list): ignore variable to load when finetuning.
            It can be specified by finetune_exclude_pretrained_params
            and the usage can refer to docs/advanced_tutorials/TRANSFER_LEARNING.md
    """
    if not (os.path.isdir(path) or os.path.exists(path + '.pdparams')):
        raise ValueError("Model pretrain path {} does not "
                         "exists.".format(path))

    logger.info(logger.coloring('Loading parameters from {}...'.format(path), 'HEADER'))

    ignore_set = set()
    state = _load_state(path)

    # ignore the parameter which mismatch the shape
    # between the model and pretrain weight.
    all_var_shape = {}
    for block in prog.blocks:
        for param in block.all_parameters():
            all_var_shape[param.name] = param.shape
    ignore_set.update([
        name for name, shape in all_var_shape.items()
        if name in state and shape != state[name].shape
    ])

    if ignore_params:
        all_var_names = [var.name for var in prog.list_vars()]
        ignore_list = filter(
            lambda var: any([re.match(name, var) for name in ignore_params]),
            all_var_names)
        ignore_set.update(list(ignore_list))

    if len(ignore_set) > 0:
        for k in ignore_set:
            if k in state:
                logger.warning('variable {} is already excluded automatically'.format(k))
                del state[k]
    fluid.io.set_program_state(prog, state)


def init_model(config, program, exe):
    """
    load model from checkpoint or pretrained_model
    """
    checkpoints = config.get('checkpoints')
    if checkpoints:
        fluid.load(program, checkpoints, exe)
        logger.info(logger.coloring("Finish initing model from {}".format(checkpoints),"HEADER"))
        return

    pretrained_model = config.get('pretrained_model')
    if pretrained_model:
        if not isinstance(pretrained_model, list):
            pretrained_model = [pretrained_model]
        for pretrain in pretrained_model:
            load_params(exe, program, pretrain)
        logger.info(logger.coloring("Finish initing model from {}".format(pretrained_model),"HEADER"))


def save_model(program, model_path, epoch_id, prefix='ppcls'):
    """
    save model to the target path
    """
    model_path = os.path.join(model_path, str(epoch_id))
    _mkdir_if_not_exist(model_path)
    model_prefix = os.path.join(model_path, prefix)
    fluid.save(program, model_prefix)
    logger.info(logger.coloring("Already save model in {}".format(model_path),"HEADER"))
