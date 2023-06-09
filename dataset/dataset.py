import os
import tqdm
import torch
import re
import collections
import imageio
import random

from tqdm import tqdm
from torch.utils.data import Dataset

import pandas as pd
import numpy as np
import scipy.io as sio

# rose@ntu.edu.sg
sample_num_level1 = 512
sample_num_level2 = 128

TRAIN_IDS = [1, 3, 5, 7, 9]
TEST_IDS = [2, 4, 6, 8, 10]
TRAIN_VALID_IDS = ([], [])
compiled_regex = re.compile('.*S(\d{3})C(\d{3})P(\d{3})R(\d{3})A(\d{3}).*')


# SAMPLE_NUM = 2048

class NTU_RGBD(Dataset):
    """NTU depth human masked datasets"""

    def __init__(self, root_path, opt,
                 full_train=True,
                 test=False,
                 validation=False,
                 DATA_CROSS_VIEW=True,
                 Transform=True):

        self.DATA_CROSS_VIEW = DATA_CROSS_VIEW
        self.root_path = root_path
        self.SAMPLE_NUM = opt.SAMPLE_NUM
        self.INPUT_FEATURE_NUM = opt.INPUT_FEATURE_NUM
        self.EACH_FRAME_SAMPLE_NUM = opt.EACH_FRAME_SAMPLE_NUM
        self.T_sample_num_level1 = opt.T_sample_num_level1

        self.all_framenum = opt.all_framenum
        self.framenum = opt.framenum
        self.transform = Transform
        # self.depth_path = opt.depth_path

        self.point_vids = os.listdir(self.root_path + '/T')  # .sort()
        self.point_vids.sort()
        # print(self.point_vids)
        self.TRAIN_IDS = TRAIN_IDS
        self.TEST_IDS = TEST_IDS

        self.num_clouds = len(self.point_vids)
        print(self.num_clouds)
        self.point_data = self.load_data()

        self.set_splits()

        self.id_to_action = list(pd.DataFrame(self.point_data)['action'] - 1)
        self.id_to_vidName = list(pd.DataFrame(self.point_data)['video_cloud_name'])

        self.train = (test == False) and (validation == False)
        if DATA_CROSS_VIEW == False:
            if test:
                self.vid_ids = self.test_split_subject.copy()
            elif validation:
                self.vid_ids = self.validation_split_subject.copy()
            elif full_train:
                self.vid_ids = self.train_split_subject.copy()
            else:
                self.vid_ids = self.train_split_subject_with_validation.copy()
        else:
            if test:
                self.vid_ids = self.test_split_camera.copy()
            else:
                self.vid_ids = self.train_split_camera.copy()

        print('num_data:', len(self.vid_ids))

        # self.SAMPLE_NUM = opt.SAMPLE_NUM
        # self.INPUT_FEATURE_NUM = opt.INPUT_FEATURE_NUM

        # self.point_clouds = np.empty(shape=[self.SAMPLE_NUM, self.INPUT_FEATURE_NUM],dtype=np.float32)

    def __getitem__(self, idx):
        vid_id = self.vid_ids[idx]
        vid_name = self.id_to_vidName[vid_id]
        S_idx = vid_name[1:4]
        # print(vid_name)
        v_name = vid_name[:-4]

        ## 4DV-T motion point data
        path_T = self.root_path + '/T'
        path_cloud_npy_T = os.path.join(path_T, self.id_to_vidName[vid_id])

        all_sam = np.arange(self.all_framenum)

        if (1 == 1):  #
            frame_index = []
            for jj in range(self.framenum):
                iii = int(np.random.randint(int(self.all_framenum * jj / self.framenum),
                                            int(self.all_framenum * (jj + 1) / self.framenum)))
                frame_index.append(iii)
        if (1 == 0):  #
            frame_index = random.sample(list(all_sam), self.framenum)
        points4DV_T = np.load(path_cloud_npy_T)[frame_index, 0:self.EACH_FRAME_SAMPLE_NUM,
                      :self.INPUT_FEATURE_NUM]  # 60*512*4
        #print(points4DV_T.shape)
        ## 4DV-S motion point data
        # path_S=self.root_path+'\\S'
        # path_cloud_npy_S = os.path.join(path_S,self.id_to_vidName[vid_id])
        # matlab data(.mat) OR python data(.npy)
        # XYZ_C = sio.loadmat(path_cloud_npy)
        # print(self.id_to_vidName[vid_id])
        # points_c = XYZ_C['pc'].astype(np.float32)
        # print(path_cloud_npy)
        # points4DV_S= np.load(path_cloud_npy_S)[:,0:4]#2048*4
        # points4DV_S = np.expand_dims(points4DV_S, axis=0)#1*2048*4
        # print(points_c.shape, points_2048_f.shape)
        label = self.id_to_action[vid_id]

        # random angle rotate for data augment
        theta = np.random.rand() * 1.4 - 0.7

        if self.transform:
            ## point data augment
            points4DV_T = self.point_transform(points4DV_T, theta)
        points4DV_T = torch.tensor(points4DV_T, dtype=torch.float)
        # points4DV_S = torch.tensor(points4DV_S,dtype=torch.float)
        label = torch.tensor(label)
        return points4DV_T, label, vid_name

    def __len__(self):
        return len(self.vid_ids)

    def load_data(self):
        self.point_data = []
        for cloud_idx in tqdm(range(self.num_clouds), "Getting video info"):
            self.point_data.append(self.get_pointdata(cloud_idx))

        return self.point_data

    def get_pointdata(self, vid_id):

        vid_name = self.point_vids[vid_id]
        match = re.match(compiled_regex, vid_name)
        setup, camera, performer, replication, action = [*map(int, match.groups())]
        return {
            'video_cloud_name': vid_name,
            'video_index': vid_id,
            'video_set': (setup, camera),
            'setup': setup,
            'camera': camera,
            'performer': performer,
            'replication': replication,
            'action': action,
        }

    def set_splits(self):
        '''
        Sets the train/test splits
        Cross-Subject Evaluation:
            Train ids = 1, 2, 4, 5, 8, 9, 13, 14, 15, 16, 17, 18, 19, 25, 27,
                        28, 31, 34, 35, 38
        Cross-View Evaluation:
            Train camera views: 2, 3
        '''
        # Save the dataset as a dataframe
        dataset = pd.DataFrame(self.point_data)

        # Get the train split ids
        train_ids_camera = [2, 3]

        # Cross-Subject splits
        self.train_split_subject = list(
            dataset[dataset.performer.isin(self.TRAIN_IDS)]['video_index'])
        self.train_split_subject_with_validation = list(
            dataset[dataset.performer.isin(TRAIN_VALID_IDS[0])]['video_index'])
        self.validation_split_subject = list(
            dataset[dataset.performer.isin(TRAIN_VALID_IDS[1])]['video_index'])
        self.test_split_subject = list(
            dataset[dataset.performer.isin(self.TEST_IDS)]['video_index'])

        # Cross-View splits
        self.train_split_camera = list(
            dataset[dataset.camera.isin(train_ids_camera)]['video_index'])
        self.test_split_camera = list(
            dataset[~dataset.camera.isin(train_ids_camera)]['video_index'])

    def point_transform(self, points_xyz, y):

        anglesX = (np.random.uniform() - 0.5) * (1 / 9) * np.pi
        R_y = np.array([[[np.cos(y), 0.0, np.sin(y)],
                         [0.0, 1.0, 0.0],
                         [-np.sin(y), 0.0, np.cos(y)]]])
        R_x = np.array([[[1, 0, 0],
                         [0, np.cos(anglesX), -np.sin(anglesX)],
                         [0, np.sin(anglesX), np.cos(anglesX)]]])
        # print(R_y.shape)

        # points_c[:,:,0:3] = self.jitter_point_cloud(points_c[:,:,0:3],sigma=0.007, clip=0.04)
        points_xyz[:, :, 0:3] = self.jitter_point_cloud(points_xyz[:, :, 0:3], sigma=0.007, clip=0.04)  #

        # points_c[:,-1536:,:] = self.random_dropout_point_cloud(points_c[:,-1536:,:])
        points_xyz[:, -(self.EACH_FRAME_SAMPLE_NUM - self.T_sample_num_level1):, :] = self.random_dropout_point_cloud(
            points_xyz[:, -(self.EACH_FRAME_SAMPLE_NUM - self.T_sample_num_level1):, :])

        R = np.matmul(R_y, R_x)

        # points_c[:,:,0:3] = np.matmul(points_c[:,:,0:3],R)
        points_xyz[:, :, 0:3] = np.matmul(points_xyz[:, :, 0:3], R)

        # if np.random.rand()>0.6:
        #    for i in range(3):
        #        points_c[:,i] = points_c[:,i]+(np.random.rand()-0.5)/6
        #        points_xyz[:,i] = points_xyz[:,i]+(np.random.rand()-0.5)/6

        # print(points.shape)
        return points_xyz

    # def load_depth_from_img(self,depth_path):
    # depth_im = imageio.imread(depth_path) #im is a numpy array
    # return depth_im

    def jitter_point_cloud(self, data, sigma=0.01, clip=0.05):
        """

        :param data: Nx3 array
        :return: jittered_data: Nx3 array
        """
        M, N, C = data.shape
        # print(np.random.randn(M, N, C))#
        jittered_data = np.clip(sigma * np.random.randn(M, N, C), -1 * clip, clip).astype(np.float32)  #

        jittered_data = data + jittered_data

        return jittered_data

    def random_dropout_point_cloud(self, data):
        """
        :param data:  Nx3 array
        :return: dropout_data:  Nx3 array
        """
        M, N, C = data.shape  ##60*300*4
        dropout_ratio = 0.7 + np.random.random() / 2  # n
        # dropout_ratio = np.random.random() * p
        drop_idx = np.where(np.random.random(N) <= dropout_ratio)[0]
        dropout_data = np.zeros_like(data)
        if len(drop_idx) > 0:
            dropout_data[:, drop_idx, :] = data[:, drop_idx, :]

        # xyz_center = np.random.random(3)
        # xyz_d = 0.1+np.random.random(3)/10

        # func_x = lambda d: d>xyz_center[0] and d<(xyz_center[0]+xyz_d[0])
        # func_y = lambda d: d>xyz_center[1] and d<(xyz_center[1]+xyz_d[1])
        # func_z = lambda d: d>xyz_center[2] and d<(xyz_center[2]+xyz_d[2])
        # c_x = np.vectorize(func_x)(data[:,0])
        # c_y = np.vectorize(func_x)(data[:,0])
        # c_z = np.vectorize(func_x)(data[:,0])
        # c = c_x*c_z*c_y
        # erase_index = np.where(c)
        # dropout_data[erase_index,:] =0
        return dropout_data