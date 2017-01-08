#====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

# in the future ... <pep8 compliant>
bl_info = {
    "name": "Fisheye Viewport",
    "author": "Dalai Felinto",
    "version": (0, 9),
    "blender": (2, 7, 8),
    "location": "View 3D Tools",
    "description": "",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "3D View"}

import bpy
from bgl import *


# ############################################################
# GLSL Shaders
# ############################################################

fragment_shader ="""
#version 120

uniform sampler2D color_buffer;

void main(void)
{
    vec2 coords = gl_TexCoord[0].st;
    vec4 color = texture2D(color_buffer, coords);
    gl_FragColor = mix(color, vec4(1.0f, 0.0f, 0.0f, 1.0f), 0.5f);
}
"""


# ############################################################
# GLSL Debug
# ############################################################

def print_shader_errors(shader):
    """"""
    log = Buffer(GL_BYTE, len(fragment_shader))
    length = Buffer(GL_INT, 1)

    print('Shader Code:')
    glGetShaderSource(shader, len(log), length, log)

    line = 1
    msg = "  1 "

    for i in range(length[0]):
        if chr(log[i-1]) == '\n':
            line += 1
            msg += "%3d %s" %(line, chr(log[i]))
        else:
            msg += chr(log[i])

    print(msg)

    glGetShaderInfoLog(shader, len(log), length, log)
    print("Error in GLSL Shader:\n")
    msg = ""
    for i in range(length[0]):
        msg += chr(log[i])

    print(msg)


def print_program_errors(program):
    """"""
    log = Buffer(GL_BYTE, 1024)
    length = Buffer(GL_INT, 1)

    glGetProgramInfoLog(program, len(log), length, log)

    print("Error in GLSL Program:\n")

    msg = ""
    for i in range(length[0]):
        msg += chr(log[i])

    print (msg)


# ############################################################
# Utils
# ############################################################

def create_shader(source, program=None, type=GL_FRAGMENT_SHADER):
    """"""
    if program == None:
        program = glCreateProgram()

    shader = glCreateShader(type)
    glShaderSource(shader, source)
    glCompileShader(shader)

    success = Buffer(GL_INT, 1)
    glGetShaderiv(shader, GL_COMPILE_STATUS, success)

    if not success[0]:
        print_shader_errors(shader)
    glAttachShader(program, shader)
    glLinkProgram(program)

    return program


# ############################################################
# Operators
# ############################################################

class VIEW3D_OT_FisheyeDraw(bpy.types.Operator):
    """"""
    bl_idname = "view3d.fisheye_draw"
    bl_label = "Fisheye Draw"

    _handle_calc = None
    _handle_draw = None
    is_enabled = False

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D'

    @staticmethod
    def handle_add(self, context):
        VIEW3D_OT_FisheyeDraw._handle_draw = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_px, (context, ), 'WINDOW', 'POST_PIXEL')

    @staticmethod
    def handle_remove():
        if VIEW3D_OT_FisheyeDraw._handle_draw is not None:
            bpy.types.SpaceView3D.draw_handler_remove(VIEW3D_OT_FisheyeDraw._handle_draw, 'WINDOW')

        VIEW3D_OT_FisheyeDraw._handle_draw = None

    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if VIEW3D_OT_FisheyeDraw.is_enabled:
            VIEW3D_OT_FisheyeDraw.handle_remove()
            VIEW3D_OT_FisheyeDraw.is_enabled = False

            if context.area:
                context.area.tag_redraw()

            return {'FINISHED'}

        else:
            if not self.init(context):
                self.report({'ERROR'}, "Error initializing offscreen buffer. More details in the console")
                return {'CANCELLED'}

            VIEW3D_OT_FisheyeDraw.handle_add(self, context)
            VIEW3D_OT_FisheyeDraw.is_enabled = True

            if context.area:
                context.area.tag_redraw()

            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

    def init(self, context):
        import gpu
        scene = context.scene
        aspect_ratio = scene.render.resolution_x / scene.render.resolution_y

        try:
            self._offscreen = gpu.offscreen.new(512, int(512 / aspect_ratio), 0)
            self._texture = self._offscreen.color_texture
            self._program = create_shader(fragment_shader)

        except Exception as E:
            print(E)
            return False

        if not self._offscreen:
            return False

        return True

    def draw_callback_px(self, context):
        scene = context.scene
        aspect_ratio = scene.render.resolution_x / scene.render.resolution_y

        self._update_offscreen(context, self._offscreen)
        self._opengl_draw(self._program, self._texture, aspect_ratio, 0.2)

    def _update_offscreen(self, context, offscreen):
        scene = context.scene
        render = scene.render
        camera = scene.camera

        modelview_matrix = camera.matrix_world.inverted()
        projection_matrix = camera.calc_matrix_camera(
                render.resolution_x,
                render.resolution_y,
                render.pixel_aspect_x,
                render.pixel_aspect_y,
                )

        offscreen.draw_view3d(
                scene,
                context.space_data,
                context.region,
                projection_matrix,
                modelview_matrix)

    @staticmethod
    def _opengl_draw(program, texture, aspect_ratio, scale):
        """
        OpenGL code to draw a rectangle in the viewport
        """
        glDisable(GL_DEPTH_TEST)

        # view setup
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glOrtho(-1, 1, -1, 1, -15, 15)
        gluLookAt(0.0, 0.0, 1.0, 0.0,0.0,0.0, 0.0,1.0,0.0)

        act_tex = Buffer(GL_INT, 1)
        glGetIntegerv(GL_TEXTURE_2D, act_tex)

        viewport = Buffer(GL_INT, 4)
        glGetIntegerv(GL_VIEWPORT, viewport)

        width = int(scale * viewport[2])
        height = int(width / aspect_ratio)

        glViewport(viewport[0], viewport[1], width, height)
        glScissor(viewport[0], viewport[1], width, height)

        # draw routine
        glUseProgram(program)

        # uniforms
        uniform = glGetUniformLocation(program, "color_buffer")
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, texture)
        if uniform != -1: glUniform1i(uniform, 0)

        # draw rectangle
        glEnable(GL_TEXTURE_2D)
        glActiveTexture(GL_TEXTURE0)

        texco = [(1, 1), (0, 1), (0, 0), (1,0)]
        verco = [(1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0), (1.0, -1.0)]

        glPolygonMode(GL_FRONT_AND_BACK , GL_FILL)

        glColor4f(1.0, 1.0, 1.0, 1.0)

        glBegin(GL_QUADS)
        for i in range(4):
            glTexCoord3f(texco[i][0], texco[i][1], 0.0)
            glVertex2f(verco[i][0], verco[i][1])
        glEnd()

        # restoring settings
        glBindTexture(GL_TEXTURE_2D, act_tex[0])

        glDisable(GL_TEXTURE_2D)

        glUseProgram(0)

        # reset view
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()

        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

        glViewport(viewport[0], viewport[1], viewport[2], viewport[3])
        glScissor(viewport[0], viewport[1], viewport[2], viewport[3])


# ############################################################
# Un/Registration
# ############################################################

classes = (
        VIEW3D_OT_FisheyeDraw,
        )

def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
