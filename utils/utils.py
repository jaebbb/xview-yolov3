import random

import cv2
import numpy as np
import torch

# set printoptions
torch.set_printoptions(linewidth=320, precision=5, profile='long')
np.set_printoptions(linewidth=320, formatter={'float_kind': '{11.5g}'.format})  # format short g, %precision=5


def load_classes(path):
    """
    Loads class labels at 'path'
    """
    fp = open(path, "r")
    names = fp.read().split("\n")[:-1]
    return names


def modelinfo(model):
    nparams = sum(x.numel() for x in model.parameters())
    ngradients = sum(x.numel() for x in model.parameters() if x.requires_grad)
    print('\n%4s %70s %9s %12s %20s %12s %12s' % ('', 'name', 'gradient', 'parameters', 'shape', 'mu', 'sigma'))
    for i, (name, p) in enumerate(model.named_parameters()):
        name = name.replace('module_list.', '')
        print('%4g %70s %9s %12g %20s %12g %12g' % (
            i, name, p.requires_grad, p.numel(), list(p.shape), p.mean(), p.std()))
    print('\n%g layers, %g parameters, %g gradients' % (i + 1, nparams, ngradients))


def xview_indices2classes(indices):  # remap xview classes 11-94 to 0-61
    class_list = [11, 12, 13, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 27, 28, 29, 32, 33, 34, 35, 36, 37, 38, 40, 41,
                  42, 44, 45, 47, 49, 50, 51, 52, 53, 54, 55, 56, 57, 59, 60, 61, 62, 63, 64, 65, 66, 71, 72, 73, 74,
                  76, 77, 79, 83, 84, 86, 89, 91, 93, 94]
    return class_list[indices]


def xview_class_weights(indices):  # weights of each class in the training set, normalized to mu = 1
    weights = torch.FloatTensor(
        [0.0074, 0.0367, 0.0716, 0.0071, 0.295, 21.1*0, 0.695, 0.11, 0.363, 1.22, 0.588, 0.364, 0.0859, 0.409, 0.0894,
         0.0149, 0.0173, 0.0017, 0.163, 0.184, 0.0125, 0.0122, 0.0124, 0.0687, 0.146, 0.0701, 0.0226, 0.0191, 0.0797,
         0.0202, 0.0449, 0.0331, 0.0083, 0.0204, 0.0156, 0.0193, 0.007, 0.0064, 0.0337, 0.135, 0.0337, 0.0078, 0.0628,
         0.0843, 0.0286, 0.0083, 0.071, 0.119, 31.6*0, 0.0208, 0.109, 0.0949, 0.122, 0.425, 0.0125, 0.171, 0.237, 0.158,
         0.0373, 0.0085])

    weights = weights / weights.mean()
    return weights[indices.long()]


def plot_one_box(x, im, color=None, label=None, line_thickness=None):
    tl = line_thickness or round(0.003 * max(im.shape[0:2]))  # line thickness
    color = color or [random.randint(0, 255) for _ in range(3)]
    c1, c2 = (int(x[0]), int(x[1])), (int(x[2]), int(x[3]))
    cv2.rectangle(im, c1, c2, color, thickness=tl)
    if label:
        tf = max(tl - 1, 2)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(im, c1, c2, color, -1)  # filled
        cv2.putText(im, label, (c1[0], c1[1] - 2), 0, tl / 3, [225, 255, 255], thickness=tf, lineType=cv2.LINE_AA)


def weights_init_normal(m):
    classname = m.__class__.__name__
    if classname.find('Conv') != -1:
        torch.nn.init.normal_(m.weight.data, 0.0, 0.03)
    elif classname.find('BatchNorm2d') != -1:
        torch.nn.init.normal_(m.weight.data, 1.0, 0.03)
        torch.nn.init.constant_(m.bias.data, 0.0)


def xyxy2xywh(box):
    xywh = np.zeros(box.shape)
    xywh[:, 0] = (box[:, 0] + box[:, 2]) / 2
    xywh[:, 1] = (box[:, 1] + box[:, 3]) / 2
    xywh[:, 2] = box[:, 2] - box[:, 0]
    xywh[:, 3] = box[:, 3] - box[:, 1]
    return xywh


def compute_ap(recall, precision):
    """ Compute the average precision, given the recall and precision curves.
    Code originally from https://github.com/rbgirshick/py-faster-rcnn.
    # Arguments
        recall:    The recall curve (list).
        precision: The precision curve (list).
    # Returns
        The average precision as computed in py-faster-rcnn.
    """
    # correct AP calculation
    # first append sentinel values at the end
    mrec = np.concatenate(([0.], recall, [1.]))
    mpre = np.concatenate(([0.], precision, [0.]))

    # compute the precision envelope
    for i in range(mpre.size - 1, 0, -1):
        mpre[i - 1] = np.maximum(mpre[i - 1], mpre[i])

    # to calculate area under PR curve, look for points
    # where X axis (recall) changes value
    i = np.where(mrec[1:] != mrec[:-1])[0]

    # and sum (\Delta recall) * prec
    ap = np.sum((mrec[i + 1] - mrec[i]) * mpre[i + 1])
    return ap


# @profile
def bbox_iou(box1, box2, x1y1x2y2=True):
    # if len(box1.shape) == 1:
    #    box1 = box1.reshape(1, 4)

    """
    Returns the IoU of two bounding boxes
    """
    if x1y1x2y2:
        # Get the coordinates of bounding boxes
        b1_x1, b1_y1, b1_x2, b1_y2 = box1[:, 0], box1[:, 1], box1[:, 2], box1[:, 3]
        b2_x1, b2_y1, b2_x2, b2_y2 = box2[:, 0], box2[:, 1], box2[:, 2], box2[:, 3]
    else:
        # Transform from center and width to exact coordinates
        b1_x1, b1_x2 = box1[:, 0] - box1[:, 2] / 2, box1[:, 0] + box1[:, 2] / 2
        b1_y1, b1_y2 = box1[:, 1] - box1[:, 3] / 2, box1[:, 1] + box1[:, 3] / 2
        b2_x1, b2_x2 = box2[:, 0] - box2[:, 2] / 2, box2[:, 0] + box2[:, 2] / 2
        b2_y1, b2_y2 = box2[:, 1] - box2[:, 3] / 2, box2[:, 1] + box2[:, 3] / 2

    # get the corrdinates of the intersection rectangle
    inter_rect_x1 = torch.max(b1_x1, b2_x1)
    inter_rect_y1 = torch.max(b1_y1, b2_y1)
    inter_rect_x2 = torch.min(b1_x2, b2_x2)
    inter_rect_y2 = torch.min(b1_y2, b2_y2)
    # Intersection area
    inter_area = torch.clamp(inter_rect_x2 - inter_rect_x1, 0) * \
                 torch.clamp(inter_rect_y2 - inter_rect_y1, 0)
    # Union Area
    b1_area = (b1_x2 - b1_x1) * (b1_y2 - b1_y1)
    b2_area = (b2_x2 - b2_x1) * (b2_y2 - b2_y1)

    return inter_area / (b1_area + b2_area - inter_area + 1e-16)


def build_targets_sgrid(pred_boxes, pred_conf, pred_cls, target, anchor_wh, nA, nC, nG, anchor_grid_wh, requestPrecision):
    """
    returns nGT, nCorrect, tx, ty, tw, th, tconf, tcls
    """
    nB = len(target)  # target.shape[0]
    nS = 2  # 2x2 subgrid
    nT = [len(x) for x in target]  # torch.argmin(target[:, :, 4], 1)  # targets per image
    tx = torch.zeros(nB, nA, nS, nS, nG, nG)  # batch size (4), number of anchors (3), number of grid points (13)
    ty = torch.zeros(nB, nA, nS, nS, nG, nG)
    tw = torch.zeros(nB, nA, nS, nS, nG, nG)
    th = torch.zeros(nB, nA, nS, nS, nG, nG)
    tconf = torch.ByteTensor(nB, nA, nS, nS, nG, nG).fill_(0)
    tcls = torch.ByteTensor(nB, nA, nS, nS, nG, nG, nC).fill_(0)  # nC = number of classes
    good_anchors = torch.ByteTensor(nB, nA, nS, nS, nG, nG).fill_(0)
    TP = torch.zeros(nB, max(nT))
    FP = torch.zeros(nB, max(nT))
    FN = torch.zeros(nB, max(nT))

    for b in range(nB):
        nTb = nT[b]  # number of targets (measures index of first zero-height target box)
        if nTb == 0:
            continue
        t = target[b]  # target[b, :nTb]

        # Convert to position relative to box
        gx, gy, gw, gh = t[:, 1] * nG, t[:, 2] * nG, t[:, 3] * nG, t[:, 4] * nG
        # Get grid box indices and prevent overflows (i.e. 13.01 on 13 anchors)
        gi = torch.clamp(gx.long(), min=0, max=nG - 1)
        gj = torch.clamp(gy.long(), min=0, max=nG - 1)
        si = ((gx % 1) * nS).long()
        sj = ((gy % 1) * nS).long()

        # iou of targets-anchors (using wh only)
        box1 = t[:, 3:5] * nG
        box2 = anchor_grid_wh[:, gj, gi]
        inter_area = torch.min(box1, box2).prod(2)
        iou_anch = inter_area / (gw * gh + box2.prod(2) - inter_area + 1e-16)

        # Select best iou_pred and anchor
        iou_anch_best, a = iou_anch.max(0)  # best anchor [0-2] for each target

        # Two targets can not claim the same anchor
        if nTb > 1:
            iou_order = np.argsort(-iou_anch_best)  # best to worst
            # u = torch.cat((gi, gj, a), 0).view(3, -1).numpy()
            # _, first_unique = np.unique(u[:, iou_order], axis=1, return_index=True)  # first unique indices
            u = gi.float() * 0.4361538773074043 + gj.float() * 0.28012496588736746 + a.float() * 0.6627147212460307 + \
                si.float() * 0.38490114597266045 + sj.float() * 0.5756510141648885
            _, first_unique = np.unique(u[iou_order], return_index=True)  # first unique indices
            # print(((np.sort(first_unique) - np.sort(first_unique2)) ** 2).sum())
            i = iou_order[first_unique]
            a, gj, gi, sj, si, t = a[i], gj[i], gi[i], sj[i], si[i], t[i]
        else:
            i = 0

        tc, gx, gy, gw, gh = t[:, 0].long(), t[:, 1] * nG, t[:, 2] * nG, t[:, 3] * nG, t[:, 4] * nG

        # Coordinates
        tx[b, a, sj, si, gj, gi] = gx - (gi.float() + si.float() / nS)
        ty[b, a, sj, si, gj, gi] = gy - (gj.float() + sj.float() / nS)
        # Width and height
        tw[b, a, sj, si, gj, gi] = gw / anchor_wh[a, 0] / 5
        th[b, a, sj, si, gj, gi] = gh / anchor_wh[a, 1] / 5
        # One-hot encoding of label
        tcls[b, a, sj, si, gj, gi, tc] = 1
        tconf[b, a, sj, si, gj, gi] = 1
        good_anchors[b, :, sj, si, gj, gi] = iou_anch[:, i].reshape(nA, -1) > 0.50


        if requestPrecision:
            pred_boxes[b, a, 1, si, gj, gi, 1] += 0.5
            pred_boxes[b, a, 1, si, gj, gi, 3] += 0.5
            pred_boxes[b, a, sj, 1, gj, gi, 0] += 0.5
            pred_boxes[b, a, sj, 1, gj, gi, 2] += 0.5

            # predicted classes and confidence
            tb = torch.cat((gx - gw / 2, gy - gh / 2, gx + gw / 2, gy + gh / 2)).view(4, -1).t()  # target boxes
            pcls = torch.argmax(pred_cls[b, a, sj, si, gj, gi].cpu(), 1)
            pconf = pred_conf[b, a, sj, si, gj, gi].cpu()
            iou_pred = bbox_iou(tb, pred_boxes[b, a, sj, si, gj, gi].cpu())

            TP[b, i] = ((pconf > 0.99) & (iou_pred > 0.5) & (pcls == tc)).float()
            FP[b, i] = ((pconf > 0.99) & ((iou_pred < 0.5) | (pcls != tc))).float()  # coordinates or class are wrong
            FN[b, :nTb] = 1.0
            FN[b, i] = (pconf < 0.99).float()  # confidence score is too low (set to zero)

    ap = 0
    return tx, ty, tw, th, tconf == 1, tcls, TP, FP, FN, ap, good_anchors == 1


def build_targets(pred_boxes, pred_conf, pred_cls, target, anchor_wh, nA, nC, nG, anchor_grid_wh, requestPrecision):
    """
    returns nGT, nCorrect, tx, ty, tw, th, tconf, tcls
    """
    nB = len(target)  # target.shape[0]
    nT = [len(x) for x in target]  # torch.argmin(target[:, :, 4], 1)  # targets per image
    tx = torch.zeros(nB, nA, nG, nG)  # batch size (4), number of anchors (3), number of grid points (13)
    ty = torch.zeros(nB, nA, nG, nG)
    tw = torch.zeros(nB, nA, nG, nG)
    th = torch.zeros(nB, nA, nG, nG)
    tconf = torch.ByteTensor(nB, nA, nG, nG).fill_(0)
    good_anchors = torch.ByteTensor(nB, nA, nG, nG).fill_(0)
    tcls = torch.ByteTensor(nB, nA, nG, nG, nC).fill_(0)  # nC = number of classes
    TP = torch.zeros(nB, max(nT))
    FP = torch.zeros(nB, max(nT))
    FN = torch.zeros(nB, max(nT))

    for b in range(nB):
        nTb = nT[b]  # number of targets (measures index of first zero-height target box)
        if nTb == 0:
            continue
        t = target[b]  # target[b, :nTb]

        # Convert to position relative to box
        gx, gy, gw, gh = t[:, 1] * nG, t[:, 2] * nG, t[:, 3] * nG, t[:, 4] * nG
        # Get grid box indices and prevent overflows (i.e. 13.01 on 13 anchors)
        gi = torch.clamp(gx.long(), min=0, max=nG - 1)
        gj = torch.clamp(gy.long(), min=0, max=nG - 1)

        # iou of targets-anchors (using wh only)
        box1 = t[:, 3:5] * nG
        box2 = anchor_grid_wh[:, gj, gi]
        inter_area = torch.min(box1, box2).prod(2)
        iou_anch = inter_area / (gw * gh + box2.prod(2) - inter_area + 1e-16)

        # Select best iou_pred and anchor
        iou_anch_best, a = iou_anch.max(0)  # best anchor [0-2] for each target

        # Two targets can not claim the same anchor
        if nTb > 1:
            iou_order = np.argsort(-iou_anch_best)  # best to worst
            # u = torch.cat((gi, gj, a), 0).view(3, -1).numpy()
            # _, first_unique = np.unique(u[:, iou_order], axis=1, return_index=True)  # first unique indices
            u = gi.float() * 0.4361538773074043 + gj.float() * 0.28012496588736746 + a.float() * 0.6627147212460307
            _, first_unique = np.unique(u[iou_order], return_index=True)  # first unique indices
            # print(((np.sort(first_unique) - np.sort(first_unique2)) ** 2).sum())
            i = iou_order[first_unique]
            a, gj, gi, t = a[i], gj[i], gi[i], t[i]
        else:
            i = 0

        tc, gx, gy, gw, gh = t[:, 0].long(), t[:, 1] * nG, t[:, 2] * nG, t[:, 3] * nG, t[:, 4] * nG

        # Coordinates
        tx[b, a, gj, gi] = gx - gi.float()
        ty[b, a, gj, gi] = gy - gj.float()
        # Width and height
        tw[b, a, gj, gi] = gw / anchor_wh[a, 0] / 5
        th[b, a, gj, gi] = gh / anchor_wh[a, 1] / 5
        # One-hot encoding of label
        tcls[b, a, gj, gi, tc] = 1
        tconf[b, a, gj, gi] = 1
        good_anchors[b, :, gj, gi] = iou_anch[:, i].reshape(nA, -1) > 0.50

        if requestPrecision:
            # predicted classes and confidence
            tb = torch.cat((gx - gw / 2, gy - gh / 2, gx + gw / 2, gy + gh / 2)).view(4, -1).t()  # target boxes
            pcls = torch.argmax(pred_cls[b, a, gj, gi].cpu(), 1)
            pconf = pred_conf[b, a, gj, gi].cpu()
            iou_pred = bbox_iou(tb, pred_boxes[b, a, gj, gi].cpu())

            TP[b, i] = ((pconf > 0.99) & (iou_pred > 0.5) & (pcls == tc)).float()
            FP[b, i] = ((pconf > 0.99) & ((iou_pred < 0.5) | (pcls != tc))).float()  # coordinates or class are wrong
            FN[b, :nTb] = 1.0
            FN[b, i] = (pconf < 0.99).float()  # confidence score is too low (set to zero)

    #print((pred_conf>0.99).sum().float() / torch.numel(pred_conf))
    ap = 0
    return tx, ty, tw, th, tconf == 1, tcls, TP, FP, FN, ap, good_anchors == 1


def to_categorical(y, num_classes):
    """ 1-hot encodes a tensor """
    return torch.from_numpy(np.eye(num_classes, dtype='uint8')[y])


# @profile
def non_max_suppression(prediction, conf_thres=0.5, nms_thres=0.4):
    """
    Removes detections with lower object confidence score than 'conf_thres' and performs
    Non-Maximum Suppression to further filter detections.
    Returns detections with shape:
        (x1, y1, x2, y2, object_conf, class_score, class_pred)
    """

    output = [None for _ in range(len(prediction))]
    for image_i, image_pred in enumerate(prediction):
        # Filter out confidence scores below threshold
        image_pred = image_pred[image_pred[:, 4] > conf_thres]
        # If none are remaining => process next image
        nP = image_pred.shape[0]
        if not nP:
            continue

        # From (center x, center y, width, height) to (x1, y1, x2, y2)
        box_corner = image_pred.new(nP, 4)
        xy = image_pred[:, 0:2]
        wh = image_pred[:, 2:4] / 2
        box_corner[:, 0:2] = xy - wh
        box_corner[:, 2:4] = xy + wh
        image_pred[:, :4] = box_corner

        # Get score and class with highest confidence
        class_conf, class_pred = torch.max(image_pred[:, 5:], 1, keepdim=True)
        # Detections ordered as (x1, y1, x2, y2, obj_conf, class_conf, class_pred)
        detections = torch.cat((image_pred[:, :5], class_conf.float(), class_pred.float()), 1)
        # Iterate through all predicted classes
        unique_labels = detections[:, -1].cpu().unique()
        if prediction.is_cuda:
            unique_labels = unique_labels.cuda()
        for c in unique_labels:
            # Get the detections with the particular class
            detections_class = detections[detections[:, -1] == c]
            # Sort the detections by maximum objectness confidence
            _, conf_sort_index = torch.sort(detections_class[:, 4], descending=True)
            detections_class = detections_class[conf_sort_index]
            # Perform non-maximum suppression
            max_detections = []
            while detections_class.shape[0]:
                # Get detection with highest confidence and save as max detection
                max_detections.append(detections_class[0].unsqueeze(0))
                # Stop if we're at the last detection
                if len(detections_class) == 1:
                    break
                # Get the IOUs for all boxes with lower confidence
                ious = bbox_iou(max_detections[-1], detections_class[1:])
                # Remove detections with IoU >= NMS threshold
                detections_class = detections_class[1:][ious < nms_thres]

            max_detections = torch.cat(max_detections).data
            # Add max detections to outputs
            output[image_i] = max_detections if output[image_i] is None else torch.cat(
                (output[image_i], max_detections))

        # suppress boxes from other classes (with worse conf) if iou over threshold
        thresh = 0.5

        a = output[image_i]
        a = a[np.argsort(-a[:, 5])]  # sort best to worst
        xywh = torch.from_numpy(xyxy2xywh(a[:, :4].cpu().numpy().copy()))

        radius = 30  # area to search for cross-class ious
        for i in range(len(a)):
            if i >= len(a) - 1:
                break

            close = torch.nonzero(
                (abs(xywh[i, 0] - xywh[i + 1:, 0]) < radius) & (abs(xywh[i, 1] - xywh[i + 1:, 1]) < radius)) + i + 1

            if len(close) > 0:
                iou = bbox_iou(a[i:i + 1, :4], a[close.squeeze(), :4].reshape(-1, 4))
                bad = close[iou > thresh]
                if len(bad) > 0:
                    mask = torch.ones(len(a)).type(torch.ByteTensor)
                    mask[bad] = 0
                    a = a[mask]
                    xywh = xywh[mask]

        # if prediction.is_cuda:
        #    a = a.cuda()
        output[image_i] = a

    return output
