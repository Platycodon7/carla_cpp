# Copyright (c) # Copyright (c) 2018-2020 CVC.
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""
This module implements an agent that roams around a track following random
waypoints and avoiding other vehicles. The agent also responds to traffic lights.
It can also make use of the global route planner to follow a specified route
"""

#导入carla模块
import carla

#从agents.navigation.basic_agent模块中导入BasicAgent类
from agents.navigation.basic_agent import BasicAgent

#定义ConstantVelocityAgent，并且继承BasicAgent
class ConstantVelocityAgent(BasicAgent):
    """
    #快速了解这个类的主要功能
    ConstantVelocityAgent implements an agent that navigates the scene at a fixed velocity.
    #说明局限性
    This agent will fail if asked to perform turns that are impossible are the desired speed.
    #行为逻辑
    This includes lane changes. When a collision is detected, the constant velocity will stop,
    wait for a bit, and then start again.
    """

    #初始化一个对象的属性
    def __init__(self, vehicle, target_speed=20, opt_dict={}, map_inst=None, grp_inst=None):
        """
        Initialization the agent parameters, the local and the global planner.

            :param vehicle: actor to apply to agent logic onto
            :param target_speed: speed (in Km/h) at which the vehicle will move
            :param opt_dict: dictionary in case some of its parameters want to be changed.
                This also applies to parameters related to the LocalPlanner.
            :param map_inst: carla.Map instance to avoid the expensive call of getting it.
            :param grp_inst: GlobalRoutePlanner instance to avoid the expensive call of getting it.
        """
        #使super()调用父类的初始化方法
        super().__init__(vehicle, target_speed, opt_dict=opt_dict, map_inst=map_inst, grp_inst=grp_inst)

        #在类的实例中设置一个属性_use_basic_behavior的值为Flase解释用途
        self._use_basic_behavior = False  # Whether or not to use the BasicAgent behavior when the constant velocity is down
        #值除以3.6
        self. _target_speed = target_speed / 3.6  # [m/s]
        #获取车辆的速度
        self._current_speed = vehicle.get_velocity().length()  # [m/s]
        #在后续代码中根据某些条件进行赋值
        self._constant_velocity_stop_time = None
        #初始时还没有关联对象
        self._collision_sensor = None

        self._restart_time = float('inf')  # Time after collision before the constant velocity behavior starts again

        # 检查选项字典中是否存在 'restart_time' 键，并将其值赋给 self._restart_time
        if 'restart_time' in opt_dict:
            self._restart_time = opt_dict['restart_time']
        if 'use_basic_behavior' in opt_dict:
            self._use_basic_behavior = opt_dict['use_basic_behavior']

        self.is_constant_velocity_active = True
        # 初始化碰撞传感器
        self._set_collision_sensor()
        # 设置车辆的恒定速度为目标速度 target_speed
        self._set_constant_velocity(target_speed)

    def set_target_speed(self, speed):
        """Changes the target speed of the agent [km/h]"""
        self._target_speed = speed / 3.6
        self._local_planner.set_speed(speed)

    def stop_constant_velocity(self):
        """Stops the constant velocity behavior"""
        self.is_constant_velocity_active = False
        self._vehicle.disable_constant_velocity()
        self._constant_velocity_stop_time = self._world.get_snapshot().timestamp.elapsed_seconds

    def restart_constant_velocity(self):
        """Public method to restart the constant velocity"""
        self.is_constant_velocity_active = True
        self._set_constant_velocity(self._target_speed)

    def _set_constant_velocity(self, speed):
        """Forces the agent to drive at the specified speed"""
        self._vehicle.enable_constant_velocity(carla.Vector3D(speed, 0, 0))

    def run_step(self):
        """Execute one step of navigation."""
        if not self.is_constant_velocity_active:
            if self._world.get_snapshot().timestamp.elapsed_seconds - self._constant_velocity_stop_time > self._restart_time:
                self.restart_constant_velocity()
                self.is_constant_velocity_active = True
            elif self._use_basic_behavior:
                return super(ConstantVelocityAgent, self).run_step()
            else:
                return carla.VehicleControl()

        hazard_detected = False

        # Retrieve all relevant actors
        actor_list = self._world.get_actors()
        vehicle_list = actor_list.filter("*vehicle*")
        lights_list = actor_list.filter("*traffic_light*")

        vehicle_speed = self._vehicle.get_velocity().length()

        max_vehicle_distance = self._base_vehicle_threshold + vehicle_speed
        affected_by_vehicle, adversary, _ = self._vehicle_obstacle_detected(vehicle_list, max_vehicle_distance)
        if affected_by_vehicle:
            vehicle_velocity = self._vehicle.get_velocity()
            if vehicle_velocity.length() == 0:
                hazard_speed = 0
            else:
                hazard_speed = vehicle_velocity.dot(adversary.get_velocity()) / vehicle_velocity.length()
            hazard_detected = True

        # Check if the vehicle is affected by a red traffic light
        max_tlight_distance = self._base_tlight_threshold + 0.3 * vehicle_speed
        affected_by_tlight, _ = self._affected_by_traffic_light(lights_list, max_tlight_distance)
        if affected_by_tlight:
            hazard_speed = 0
            hazard_detected = True

        # The longitudinal PID is overwritten by the constant velocity but it is
        # still useful to apply it so that the vehicle isn't moving with static wheels
        control = self._local_planner.run_step()
        if hazard_detected:
            self._set_constant_velocity(hazard_speed)
        else:
            self._set_constant_velocity(self._target_speed)

        return control

    def _set_collision_sensor(self):
    # 获取碰撞传感器的蓝图（blueprint）
        blueprint = self._world.get_blueprint_library().find('sensor.other.collision')
        self._collision_sensor = self._world.spawn_actor(blueprint, carla.Transform(), attach_to=self._vehicle)
        self._collision_sensor.listen(lambda event: self.stop_constant_velocity())

    def destroy_sensor(self):
        if self._collision_sensor:
            self._collision_sensor.destroy()
            self._collision_sensor = None
