import os
import sys
import shutil
import struct
import fnmatch
import logging
from subprocess import check_output, CalledProcessError, call, STDOUT
from common import JandroidException


class AppExtractor:
    """Class to extract APKs/dex/etc from one of various locations."""

    def __init__(self, base_dir, app_dir,
                 adb_path, pull_location='device'):
        """Sets paths and app extraction location.
        
        :param base_dir: string specifying path to the base/root directory 
            (contains src/, templates/, etc)
        :param app_dir: string specifying path to the directory containing the 
            applications under analysis
        :param adb_path: string specifying path to the Android adb executable
        :param pull_location: string specifying location to pull apps from -
            can be one of "device", "ext4", "img"
        :raises JandroidException: an exception is raised if app folder cannot 
            be created
        """
        # Set paths.
        self.path_base_dir = base_dir        
        self.path_platform_tools = adb_path

        # Path to app folder
        #  (i.e., where apps should be stored after being pulled).
        #  Folder is created if it doesn't exist.
        self.path_app_folder = app_dir

        # Test if app folder exists, and if not, create it.
        if not os.path.isdir(self.path_app_folder):
            try:
                os.makedirs(self.path_app_folder)
            except Exception as e:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': FolderCreateError',
                        'reason': str(e)
                    }
                )

        # Set pull location.
        self.pull_location = pull_location

    def fn_extract_apps(self):
        """Determines which function to call based on pull location."""
        logging.info('Extracting apps from device or image.')
        if self.pull_location == 'device':
            inst_adb_pull = ADBPull(self.path_platform_tools)
            inst_adb_pull.fn_pull_from_device()
        elif self.pull_location == 'ext4':
            inst_ext4_extractor = Ext4Extractor(self.path_app_folder)
            inst_ext4_extractor.fn_extract_from_ext4()
        elif self.pull_location == 'img':
            inst_image_extractor = ImageExtractor(self.path_app_folder)
            inst_image_extractor.fn_pull_from_image()


class ADBPull:
    """Class to pull APKs from an attached Android device or VM."""

    def __init__(self, adb_path):
        """Sets path to ADB executable.
        
        :param adb_path: string specifying path to ADB executable
        """
        self.path_platform_tools = adb_path
        
    def fn_pull_from_device(self):
        """Pulls APKs from an attached Android device via ADB.
        
        :raises JandroidException: an exception is raised if any ADB 
            command should fail.
        """
        logging.debug('Pulling APKs from device.')

        # First execute 'adb devices',
        #  to make sure there is a single device attached.
        try:
            self.fn_test_connected_devices()
        except JandroidException as e:
            raise

        # Get list of packages.
        try:
            result = self.fn_execute_adb(
                ['shell', 'pm', 'list', 'packages']
            )
        except JandroidException as e:
            raise JandroidException(
                {
                    'type': e.args[0]['type'],
                    'reason': 'Error getting package list via ADB. '
                              + e.args[0]['reason']
                }
            )

        for pkg in result.split('\n'):
            # Get path-to-APK.
            pkg = pkg.replace('package:', '')
            try:
                path_to_pkg = self.fn_execute_adb(
                    ['shell', 'pm', 'path', pkg]
                )
            except JandroidException as e:
                raise JandroidException(
                    {
                        'type': e.args[0]['type'],
                        'reason': 'Error getting package path '
                                  + 'via ADB. '
                                  + e.args[0]['reason']
                    }
                )
            # Pull the APK.
            self.fn_pull_apk(pkg, path_to_pkg)

    def fn_pull_apk(self, pkg, path_to_pkg):
        """Pulls an individual APK file.
        
        :param pkg: package name string
        :param path_to_pkg: string specifying path to package (on Android)
        :raises JandroidException: an exception is raised if any ADB 
            command should fail.
        """
        logging.debug(
            'Pulling package ' + pkg + ' from ' + path_to_pkg
        )
        
        # Remove the "package:" string from path.
        path_to_apk = path_to_pkg.replace('package:', '').strip()
        
        # Pull APK (or raise error on failure).
        try:
            pull_result = self.fn_execute_adb(
                ['pull', path_to_apk, self.path_app_folder]
            )
        except JandroidException as e:
            if (e.args[0]['type'] == 'ADBError'):
                # This is an error thrown when attempting to
                #  execute ADB. Probably fatal.
                raise JandroidException(
                    {
                        'type': e.args[0]['type'],
                        'reason': 'Error pulling APK via ADB. '
                                  + e.args[0]['reason']
                    }
                )
            elif (e.args[0]['type'] == 'ADBExecuteError'):
                # This might be a 'Permission Denied'.
                #  We ignore this type of error for now.
                pass

    def fn_test_connected_devices(self):
        """Tests to make sure a single device is connected.
        
        This function runs 'adb devices' to make sure a device is attached. 
        Only one Android device (or VM) should be returned.
        
        :raises JandroidException: an exception is raised if more or less 
            than one device is returned by 'adb devices'
        """
        logging.debug('Testing for connected devices.')
        result = self.fn_execute_adb(['devices'])
        result_text_as_list = [
            f for f in result.split('\n')
            if 'daemon' not in f
        ]
        device_list = list(filter(None, result_text_as_list[1:]))
        logging.debug(
            'Device list: \n\t '
            + result.replace('\n','\n\t ')
        )
        if len(device_list) < 1:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': DeviceError',
                    'reason': 'No Android devices detected.'
                }
            )
        if len(device_list) > 1:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': DeviceError',
                    'reason': 'More than one Android device '
                              + 'attached.'
                }
            )

    def fn_execute_adb(self, cmd):
        """Execute the provided ADB command.
        
        :param cmd: the ADB command string to execute
        :returns: the result string from executing the ADB command
        """
        adb_cmd = [self.path_platform_tools] + cmd
        result = None

        try:
            # Format the output a little.
            result = check_output(adb_cmd, stderr=STDOUT)
            result = result.decode('UTF-8')
            result = result.replace('\r','').strip()
        except CalledProcessError as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': ADBExecuteError',
                    'reason': str(e)
                }
            )
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': ADBError',
                    'reason': str(e)
                }
            )

        return result


class ImageExtractor:
    """Class to extract Android applications from a .img file.
    
    This class actually only performs the extraction of a sparse image 
    from a .img file. It then calls the SparseToExt4, which converts the 
    sparse image to .ext4. The SparseToExt4 class then calls Ext4Extractor 
    to extract Android applications from the .ext4 file.
    """

    def __init__(self, app_folder):
        """Sets the path to the application folder.
        
        :param app_folder: string specifying path to application folder
        """
        self.path_app_folder = app_folder

    def fn_pull_from_image(self):
        """Enumerate img files and initiate extraction."""
        logging.debug('Extracting files from image.')
        
        # Enumerate .img files within app folder.
        images_to_pull_from = []
        for root, dirs, filenames in os.walk(self.path_app_folder):
            for filename in fnmatch.filter(filenames, '*.img'):
                images_to_pull_from.append(os.path.join(root, filename))
        
        # For each .img file, extract different images (only sparse image 
        #  supported at present).
        for image_to_pull_from in images_to_pull_from:
            try:
                self.fn_identify_image_type_from_header(image_to_pull_from)
            except JandroidException:
                raise
            except Exception as e:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': ImageExtractError',
                        'reason': str(e)
                    }
                )
            
    def fn_identify_image_type_from_header(self, path_to_img_file):
        """Identify image type from the magic header and initiate extraction.
        
        This function specifies possible headers for different types of .img 
        files (at present, only sparse images are supported). It then looks 
        for the presence of (one of) these headers within the input .img file 
        and initiates the appropriate extraction function.
        
        :param path_to_img_file: string specifying path to the .img file
        """
        # Dictionary containing headers for different .img types.
        # Only contains a single key - for sparse images - at present.
        # Each sub-object (corresponding to an image type) will contain
        #  the magic header that is used to identify the image type, as
        #  well as the extraction function to execute.
        magic_headers = {
            'android_sparse_image': {
                'header': '3AFF26ED',
                'function': \
                    SparseToExt4(self.path_app_folder
                    ).fn_convert_sparse_to_ext4
            }
        }

        # Go through each header type in turn, checking the input .img file
        #  for the presence of the header.
        for magic_header in magic_headers:
            # Different magic headers may have a different number of bytes.
            # We get this number from the dictionary object. Say, x bytes.
            num_bytes = int(len(magic_headers[magic_header]['header'])/2)
            
            # Open the .img file in Binary Read mode and check the first x
            #  bytes to see if they match the magic bytes.
            with open(path_to_img_file, "rb") as image_file:
                header_bytes = image_file.read(num_bytes).hex()
                # If the magic header matches the value in our dictionary,
                #  execute the associated extraction function (as specified
                #  in the dictionary).
                if (header_bytes.lower() == 
                        magic_headers[magic_header]['header'].lower()):
                    magic_headers[magic_header]['function'](path_to_img_file)


class SparseToExt4:
    """Class to extract .ext4 from a sparse image."""

    def __init__(self, app_folder):
        """Sets the path to the app folder.
        
        :param app_folder: string specifying path to app folder.
        """
        self.path_app_folder = app_folder
        
    def fn_convert_sparse_to_ext4(self, path_to_img_file):
        """Extracts ext4 files from Android sparse image.
        
        Extraction process is based on 
        https://android.googlesource.com/platform/system/core/+/master/ \
        libsparse/sparse_format.h
        
        Ext4 file will be written to same directory as the sparse image.
        
        :param path_to_img_file: string specifying path to sparse image file.
        :raises JandroidException: an exception is raised if the magic header 
            is incorrect, or if any subsequent byte values are not as expected.
        """
        logging.debug('Extracting files from Android sparse image.')

        # Open an output file in Binary Write mode.
        out_file_path = os.path.join(self.path_app_folder, 'temp.ext4')
        out_file = open(out_file_path, 'wb')

        # Open the sparse image file in Binary Read mode.
        try:
            image_file = open(path_to_img_file, "rb")
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': ImageOpenError',
                    'reason': 'Unable to open file '
                              + path_to_img_file
                              + ' in binary read mode: '
                              + str(e)
                }
            )

        # Unpack bytes and analyse. This will result in an Ext4 file.
        try:
            magic_header = struct.unpack('<I', image_file.read(4))[0]
            if magic_header != 0xed26ff3a:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidMagicHeader',
                        'reason': 'Error reading header bytes '
                                  + 'or invalid magic header.'
                    }
                )
            major_version = struct.unpack('<H', image_file.read(2))[0]
            if major_version != 0x01:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidVersionHeader',
                        'reason': 'Error reading header bytes '
                                  + 'or unsupported major version.'
                    }
                )
            minor_version = struct.unpack('<H', image_file.read(2))[0]
            if minor_version != 0x00:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidVersionHeader',
                        'reason': 'Error reading header bytes '
                                  + 'or unsupported minor version.'
                    }
                )
            file_hdr_sz = struct.unpack('<H', image_file.read(2))[0]
            if file_hdr_sz != 28:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidNumFileHeaderSize',
                        'reason': 'Invalid file header size.'
                    }
                )
            chunk_hdr_sz = struct.unpack('<H', image_file.read(2))[0]
            if chunk_hdr_sz != 12:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidNumChunkHeaderSize',
                        'reason': 'Invalid chunk header size.'
                    }
                )
            blk_sz = struct.unpack('<I', image_file.read(4))[0]
            if blk_sz%4 > 0:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': InvalidBlkSize',
                        'reason': 'Invalid block size (not '
                                  + 'multiple of 4).'
                    }
                )
            total_blks = struct.unpack('<I', image_file.read(4))[0]
            total_chunks = struct.unpack('<I', image_file.read(4))[0]
            image_checksum = struct.unpack('<I', image_file.read(4))[0]
            
            logging.debug(
                'Read header info from sparse image file:\n\t '
                + 'Major version: ' + str(major_version) + '\n\t '
                + 'Minor version: ' + str(minor_version) + '\n\t '
                + 'File header size: ' + str(file_hdr_sz) + '\n\t '
                + 'Chunk header size: ' + str(chunk_hdr_sz) + '\n\t '
                + 'Block size in bytes: ' + str(blk_sz) + '\n\t '
                + 'Total blocks: ' + str(total_blks) + '\n\t '
                + 'Total chunks: ' + str(total_chunks) + '\n\t '
                + 'Image checksum: ' + str(image_checksum) + '\n\t '
            )
            
            chunk_offset = 0
            for i in range(1, total_chunks+1):
                # Chunk header.
                chunk_type = struct.unpack('<H', image_file.read(2))[0]
                reserved1 = struct.unpack('<H', image_file.read(2))[0]
                chunk_sz = struct.unpack('<I', image_file.read(4))[0]
                total_sz = struct.unpack('<I', image_file.read(4))[0]
                
                logging.debug(
                    'Header information from chunk:\n\t '
                    + 'Chunk_type: ' + str(hex(chunk_type)) + '\n\t '
                    + 'Chunk size: ' + str(chunk_sz) + '\n\t '
                    + 'Total size: ' + str(total_sz) + '\n\t '
                    + 'Data size: ' + str(total_sz - 12)
                )
                if chunk_type == 0xCAC1:
                    #raw
                    data_size = chunk_sz * blk_sz
                    data_bytes = image_file.read(data_size)
                    out_file.seek(chunk_offset * blk_sz)
                    out_file.write(data_bytes)
                elif chunk_type == 0xCAC2:
                    #fill
                    # TODO: Check for correctness.
                    data_size = 4
                    data_bytes = image_file.read(data_size)
                    out_file.seek(chunk_offset * blk_sz)
                    out_file.write(data_bytes)
                elif chunk_type == 0xCAC3:
                    #don't care
                    if total_sz - 12 != 0:
                        logging.error(
                            'Don\'t care chunk has non-zero bytes!'
                        )
                        break
                elif chunk_type == 0xCAC4:
                    #crc32
                    data_size = 4
                    data_bytes = image_file.read(data_size)
                # Increment offset.
                chunk_offset += chunk_sz            
        except Exception as e:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': ByteReadError',
                    'reason': 'Error analysing sparse image '
                              + path_to_img_file
                              + ': '
                              + str(e)
                }
            )
        out_file.close()

        # Now extract files from ext4.
        inst_ext4_extractor = Ext4Extractor(self.path_app_folder)
        inst_ext4_extractor.fn_extract_from_ext4(out_file_path)


# Class for extracting APK (and DEX/etc) files from a system ext4 image.
# 
class Ext4Extractor:
    """Class for extracting APK (and DEX/etc) files from an ext4 image."""

    def __init__(self, app_folder):
        """Sets path to app folder. Initialises other variables.
        
        :param app_folder: string specifying path to ext4 image file
        """
        self.ext4_filepath = None
        self.block_size = None
        self.block_group_size = None
        self.num_block_groups = None
        self.path_app_folder = app_folder

    def fn_extract_from_ext4(self, ext4_filepath=None):
        """Extracts Android application files from EXT4 image.
        
        This function calls multiple other functions to accomplish 
        the following:
        - First analyse superblock to get info regarding block size/count 
        and inode size/count.
        - Then analyse group descriptor table to get inode table locations.
        - Then go through each inode table, get directory listings, and 
        subsequently filenames.
        - Find the inodes corresponding to APK files and extract.
        
        Based on https://ext4.wiki.kernel.org/index.php/Ext4_Disk_Layout
        
        Files are extracted to the same folder as the ext4 image. 
        Nothing is returned.
        
        :param ext4_filepath: string specifying path to ext4 file. If not 
            specified, the function will look for an ext4 file within the 
            app folder
        :raises JandroidException: an exception is thrown if more than one 
            ext4 file is found in the app folder, or if no files are found
        """
        # If no ext4 file is specified, then see if app folder contains any.
        if ext4_filepath == None:
            ext4_to_pull_from = []
            for root, dirs, filenames in os.walk(self.path_app_folder):
                for filename in fnmatch.filter(filenames, '*.ext4'):
                    ext4_to_pull_from.append(os.path.join(root, filename))
            # If no files are identified, then we have nothing to analyse.
            if len(ext4_to_pull_from) < 1:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': Ext4Error',
                        'reason': 'No ext4 files found in app folder.'
                    }
                )
            # We don't support more than one ext4 analysis at a time.
            elif len(ext4_to_pull_from) > 1:
                raise JandroidException(
                    {
                        'type': str(os.path.basename(__file__))
                                + ': Ext4Error',
                        'reason': 'More than one ext4 files found '
                                  + 'in app folder.'
                    }
                )
            self.ext4_filepath = ext4_to_pull_from[0]
        else:
            self.ext4_filepath = ext4_filepath

        logging.info(
            'Extracting files from ext4: '
            + self.ext4_filepath
        )

        ### Start analysis ###
        # Analyse superblock in block group 0.
        self.fn_analyse_super_block()
        # Analyse group descriptor in block group 0.
        self.fn_get_group_descriptor_table()
        # Analyse the inode tables to get file/dir info.
        self.fn_analyse_inode_tables()

    def fn_analyse_super_block(self):
        """Analyses the superblock in block group 0.
        
        The superblock contains a lot of information that we will require 
        later on. These are set as class attributes. 
        We do also read a lot of data that we don't use.
        
        Does not return anything.
        
        :raises JandroidException: an exception is raised if unsupported 
            modes are identified.
        """
        # Open the file in binary read mode.
        ext4_file = open(self.ext4_filepath, "rb")
        # First 1024 bytes in BG0 are padding.
        ext4_file.read(1024)
        ### Read superblock ###
        # A superblock has 1024 bytes of data.
        ext4_super_block = ext4_file.read(1024)
        s_inodes_count = \
            struct.unpack('<I', ext4_super_block[0:4])[0] # Total inode count.
        s_blocks_count_lo = \
            struct.unpack('<I', ext4_super_block[4:8])[0] # Total block count.
        s_r_blocks_count_lo = \
            struct.unpack('<I', ext4_super_block[8:12])[0]
        s_free_blocks_count_lo = \
            struct.unpack('<I', ext4_super_block[12:16])[0]
        s_free_inodes_count = \
            struct.unpack('<I', ext4_super_block[16:20])[0]
        s_first_data_block = \
            struct.unpack('<I', ext4_super_block[20:24])[0]
        s_log_block_size = \
            struct.unpack('<I', ext4_super_block[24:28])[0]
        self.block_size = 2 ** (10 + s_log_block_size)
        if self.block_size == 1024:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': Ext4Error',
                    'reason': 'Unsupported block size.'
                }
            )
        s_log_cluster_size = \
            struct.unpack('<I', ext4_super_block[28:32])[0]
        s_blocks_per_group = \
            struct.unpack('<I', ext4_super_block[32:36])[0]
        self.block_group_size = \
            self.block_size * s_blocks_per_group
        self.num_block_groups = \
            int(os.path.getsize(self.ext4_filepath)/self.block_group_size)
        s_clusters_per_group = \
            struct.unpack('<I', ext4_super_block[36:40])[0]
        s_inodes_per_group = \
            struct.unpack('<I', ext4_super_block[40:44])[0]
        self.inodes_per_group = \
            s_inodes_per_group
        s_mtime = \
            struct.unpack('<I', ext4_super_block[44:48])[0]
        s_wtime = \
            struct.unpack('<I', ext4_super_block[48:52])[0]
        s_mnt_count = \
            struct.unpack('<H', ext4_super_block[52:54])[0]
        s_max_mnt_count = \
            struct.unpack('<H', ext4_super_block[54:56])[0]
        s_magic = \
            struct.unpack('<H', ext4_super_block[56:58])[0]
        if s_magic != 0xEF53:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': Ext4Error',
                    'reason': 'Imvalid magic number in superblock.'
                }
            )
        s_state = \
            struct.unpack('<H', ext4_super_block[58:60])[0]
        s_errors = \
            struct.unpack('<H', ext4_super_block[60:62])[0]
        s_minor_rev_level = \
            struct.unpack('<H', ext4_super_block[62:64])[0]
        s_lastcheck = \
            struct.unpack('<I', ext4_super_block[64:68])[0]
        s_checkinterval = \
            struct.unpack('<I', ext4_super_block[68:72])[0]
        s_creator_os = \
            struct.unpack('<I', ext4_super_block[72:76])[0]
        s_rev_level = \
            struct.unpack('<I', ext4_super_block[76:80])[0]
        s_def_resuid = \
            struct.unpack('<H', ext4_super_block[80:82])[0]
        s_def_resgid = \
            struct.unpack('<H', ext4_super_block[82:84])[0]
        s_first_ino = \
            struct.unpack('<I', ext4_super_block[84:88])[0]
        s_inode_size = \
            struct.unpack('<H', ext4_super_block[88:90])[0]
        self.inode_size = \
            s_inode_size
        s_block_group_nr = \
            struct.unpack('<H', ext4_super_block[90:92])[0]
        s_feature_compat = \
            struct.unpack('<I', ext4_super_block[92:96])[0]
        if ((s_feature_compat & 0x10) == 0x10):
            self.has_reserved_gdt = 1
            self.num_reserved_gdt_entries = \
                struct.unpack('<H', ext4_super_block[206:208])[0]
        else:
            self.has_reserved_gdt = 0
        # Next section (compatibility).
        s_feature_incompat = \
            struct.unpack('<I', ext4_super_block[96:100])[0]
        # Support for 64-bit.
        self.INCOMPAT_64BIT = 0
        if ((s_feature_incompat & 0x80) == 0x80):
            self.INCOMPAT_64BIT = 1
        if self.INCOMPAT_64BIT != 0:
            raise JandroidException(
                {
                    'type': str(os.path.basename(__file__))
                            + ': Ext4Error',
                    'reason': 'No support for 64-bit.'
                }
            )
        # Directories store file type info.
        self.INCOMPAT_FILETYPE = 0
        if ((s_feature_incompat & 0x2) == 0x2):
            self.INCOMPAT_FILETYPE = 1
        # Data in inode.
        self.INCOMPAT_INLINE_DATA = 0
        if ((s_feature_incompat & 0x8000) == 0x8000):
            self.INCOMPAT_INLINE_DATA = 1

        # Readonly-compatible feature set.
        s_feature_ro_compat = \
            struct.unpack('<I', ext4_super_block[100:104])[0]
        # Check for large files.
        if ((s_feature_ro_compat & 0x8) == 0x8):
            self.RO_COMPAT_HUGE_FILE = 1
        else:
            self.RO_COMPAT_HUGE_FILE = 0

        logging.debug(
            'Superblock details:\n\t '
            + 'Total inode count ' + str(s_inodes_count) + '\n\t '
            + 'Total block count ' + str(s_blocks_count_lo) + '\n\t '
            + 'Log block size ' + str(s_log_block_size) + '\n\t '
            + 'Block size ' + str(self.block_size) + '\n\t '
            + 'Blocks per group ' + str(s_blocks_per_group) + '\n\t '
            + 'Inode size ' + str(s_inode_size) + '\n\t '
            + 'Inodes per group ' + str(s_inodes_per_group) + '\n\t '
            + 'Block group size ' + str(self.block_group_size) + '\n\t '
            + 'Number of block groups ' + str(self.num_block_groups) + '\n\t '
            + 'Size of inode structure (bytes) ' + str(s_inode_size) + '\n\t '
            + 'Current block group number ' + str(s_block_group_nr) + '\n\t '
            )
        ext4_file.close()

    def fn_get_group_descriptor_table(self):
        """Gets information about inode tables."""
        ext4_file = open(self.ext4_filepath, "rb")
        # Skip the superblock.
        ext4_file.seek(self.block_size, 0)
        self.block_group_data = {}
        # Read block group descriptor.
        # This is always 32 bytes. (We don't support 64-bit).
        for i in range(self.num_block_groups):            
            ext4_group_desc = ext4_file.read(32)
            bg_block_bitmap_lo = struct.unpack('<I', ext4_group_desc[0:4])[0]
            bg_inode_bitmap_lo = struct.unpack('<I', ext4_group_desc[4:8])[0]            
            bg_inode_table_lo = struct.unpack('<I', ext4_group_desc[8:12])[0]
            bg_free_blocks_count_lo = \
                struct.unpack('<H', ext4_group_desc[12:14])[0]
            bg_free_inodes_count_lo = \
                struct.unpack('<H', ext4_group_desc[14:16])[0]
            bg_used_dirs_count_lo = \
                struct.unpack('<H', ext4_group_desc[16:18])[0]
            bg_flags = struct.unpack('<H', ext4_group_desc[18:20])[0]
            logging.debug(
                'Block group data for group ' + str(i) + '\n\t '
                + 'Location of block bitmap ' + str(bg_block_bitmap_lo) + '\n\t '
                + 'Location of inode bitmap ' + str(bg_inode_bitmap_lo) + '\n\t '
                + 'Location of inode table ' + str(bg_inode_table_lo) + '\n\t '
                + 'Free block count ' + str(bg_free_blocks_count_lo) + '\n\t '
                + 'Free inode count ' + str(bg_free_inodes_count_lo) + '\n\t '
                + 'Directory count ' + str(bg_used_dirs_count_lo) + '\n\t '
                + 'Flags ' + str(bg_flags)
            )
            # Update block group object.
            self.block_group_data[i] = {}
            self.block_group_data[i]['inode_table_location'] = bg_inode_table_lo
            self.block_group_data[i]['inode_bitmap_location'] = \
                bg_inode_bitmap_lo
            inode_used_count = \
                self.inodes_per_group - bg_free_inodes_count_lo
            self.block_group_data[i]['used_inodes'] = inode_used_count
        ext4_file.close()

    def fn_analyse_inode_tables(self):
        """For each inode table, for each inode entry, starts analysis.
        
        Each inode corresponds to a file/folder. This function identifies 
        the different inode table locations, as well as the indices of inodes 
        within each table. It then calls another method to identify the 
        directory inodes, and find out the names of files contained within 
        each directory, to then filter out and extract only the .apk files 
        (via another function).
        
        Returns nothing.
        """
        for index in self.block_group_data:
            if self.block_group_data[index]['used_inodes'] <= 0:
                continue
            inode_table_location = \
                self.block_group_data[index]['inode_table_location']
            # The index is the position of an inode entry within the inode
            #  table. There will be a total of self.inodes_per_group inode
            #  entries within one inode table.
            for inode_index in range(self.inodes_per_group):
                self.fn_analyse_dir_inode_find_application_nodes(
                    inode_table_location,
                    inode_index
                )

    def fn_analyse_dir_inode_find_application_nodes(self, seek_location,
                                                    inode_index):
        """Analyses inodes pertaining to directories.
        
        Looks for directory inodes and enumerates the files within them. 
        Then filters out .apk files and calls a different function to 
        extract them. 
            
        :param seek_location: integer value specifying inode table location
        :param inode_index: integer value specifying inode index within table
        """
        # Open the file in binary read mode.
        ext4_file = open(self.ext4_filepath, "rb")
        ext4_file.seek((
            (seek_location * self.block_size)
             + (inode_index * self.inode_size)),
            0
        )
        ext4_inode = ext4_file.read(self.inode_size)
        i_mode = struct.unpack('<H', ext4_inode[0:2])[0]
        # We only care about directories (that contain references
        #  to APKs/dex/etc).
        # 0x4000 denotes directories.
        if ((i_mode & 0x4000) != 0x4000):
            ext4_file.close()
            return
        i_size_lo = struct.unpack('<I', ext4_inode[4:8])[0]
        # Analyse inode flags.
        i_flags = struct.unpack('<I', ext4_inode[32:36])[0]
        # Extent flags.
        if ((i_flags & 0x80000) == 0x80000):
            EXT4_EXTENTS_FL = 1
        else:
            EXT4_EXTENTS_FL = 0
        # Hashed index flags.
        if ((i_flags & 0x1000) == 0x1000):
            EXT4_INDEX_FL = 1
        else:
            EXT4_INDEX_FL = 0
        if EXT4_INDEX_FL == 1:
            logging.debug('Hashed indexes not supported.')
            ext4_file.close()
        # Top of dir hierarchy flag.
        if ((i_flags & 0x20000) == 0x20000):
            EXT4_TOPDIR_FL = 1
        else:
            EXT4_TOPDIR_FL = 0

        i_blocks_lo = struct.unpack('<I', ext4_inode[28:32])[0]
        union_osd2 = ext4_inode[116:116+12]
        i_blocks_high = struct.unpack('<H', union_osd2[0:2])[0]
        logging.debug(
            'Information about this inode:\n\t '
            + 'Lower 32-bits of size in bytes ' + str(i_size_lo) + '\n\t '
            + 'Lower 32-bits of "block" count ' + str(i_blocks_lo)
        )
        # Get i_block.
        i_block = ext4_inode[40:100]
        # If the inode doesn't use extents, pass.
        if EXT4_EXTENTS_FL != 1:
            logging.warning('Non-extent. Skipping...')
            ext4_file.close()
            return
        # Analyse extent tree header. Format: ext4_extent_header.
        # Check the magic number.
        eh_magic = struct.unpack('<H', i_block[0:2])[0]
        if eh_magic != 0xF30A:
            logging.error('Invalid magic number for extent.')
            ext4_file.close()
            return
        eh_entries = struct.unpack('<H', i_block[2:4])[0]
        eh_max = struct.unpack('<H', i_block[4:6])[0]
        eh_depth = struct.unpack('<H', i_block[6:8])[0]
        logging.debug(
            'Inode extent tree:\n\t '
            + 'Number of valid entries following the header '
            + str(eh_entries) + '\n\t '
            + 'Maximum number of entries that could follow the header '
            + str(eh_max) + '\n\t '
            + 'Depth of this extent node in the extent tree '
            + str(eh_depth)
        )
        if eh_depth > 0:
            ei_block = struct.unpack('<I', i_block[12:16])[0]
            ei_leaf_lo = struct.unpack('<I', i_block[16:20])[0]
            ext4_file.close()
            return
        # Get leaf nodes. Format: ext4_extent
        if eh_entries <= 0:
            logging.warning('No entries.')
            ext4_file.close()
            return
        ee_block = struct.unpack('<I', i_block[12:16])[0]
        ee_len = struct.unpack('<H', i_block[16:18])[0]
        if ee_len > 32768:
            ee_len = ee_len - 32768
        ee_start_hi = struct.unpack('<H', i_block[18:20])[0]
        ee_start_lo = struct.unpack('<I', i_block[20:24])[0]

        ext4_file.seek(ee_start_lo * self.block_size)
        ext4_dir_entry_2 = ext4_file.read(ee_len * self.block_size)        
        i = 0
        while True:            
            try:
                inode_number = \
                    struct.unpack('<I', ext4_dir_entry_2[i+0:i+4])[0]
                rec_len = \
                    struct.unpack('<H', ext4_dir_entry_2[i+4:i+6])[0]
                if rec_len == 0:
                    break
                if inode_number == 0:
                    # Unused directory entry.
                    i = i+ rec_len
                    continue
                if self.INCOMPAT_FILETYPE == 1:
                    name_len = \
                        struct.unpack('<B', ext4_dir_entry_2[i+6:i+7])[0]
                    file_type = \
                        struct.unpack('<B', ext4_dir_entry_2[i+7:i+8])[0]
                else:
                    name_len = \
                        struct.unpack('<H', ext4_dir_entry_2[i+6:i+8])[0]
                filename = ext4_dir_entry_2[i+8:i+8+name_len].decode("utf-8")
                remaining_bytes = ext4_dir_entry_2[i+8+name_len:]
                # We only want APK files.
                if (filename.lower().endswith('.apk')):
                    logging.debug(
                        'Directory information:\n\t '
                        + 'Number of the inode that '
                        + 'this directory entry points to '
                        + str(inode_number) + '\n\t '
                        + 'Length of this directory entry '
                        + str(rec_len) + '\n\t '
                        + 'Length of the file name '
                        + str(name_len) + '\n\t '
                        + 'Filename ' + filename
                    )
                    self.fn_analyse_file_inode(inode_number, filename)
                i = i+ rec_len
            except Exception as e:
                break
        ext4_file.close()

    def fn_analyse_file_inode(self, apk_inode_number, apk_name):
        """Analyses the file inode.
        
        This function tries to retrieve the bytes corresponding an APK 
        file inode. If successful, it writes the APK file out to the app 
        folder, with the same file name as it has on the ext4 file.
        Does not return anything.
        
        :param apk_inode_number: inode number containing the APK file (integer)
        :param apk_name: string value to be used as the name of the APK 
            when writing to file.
        """
        logging.debug('Trying to recover file ' + apk_name)
        # Calculate the block group containing the inode.
        number_of_block_group_containing_inode = \
            int((apk_inode_number - 1) / self.inodes_per_group)
        # Calculate the offset into the block group.
        offset_into_group_table = \
            (apk_inode_number - 1) % self.inodes_per_group

        # Open the file in binary read mode.
        ext4_file = open(self.ext4_filepath, "rb")
        start_of_inode_table_within_bg = \
            self.block_group_data[number_of_block_group_containing_inode]\
            ['inode_table_location']
        ext4_file.seek((start_of_inode_table_within_bg * self.block_size
                        + (offset_into_group_table * self.inode_size)),
                        0)
        ext4_inode = ext4_file.read(self.inode_size)

        # Get file mode.
        i_mode = struct.unpack('<H', ext4_inode[0:2])[0]
        # If for some reason, the file is not a file, return.
        if ((i_mode & 0x8000) != 0x8000):
            ext4_file.close()
            return
        # Lower 32-bits of size in bytes (unused).
        i_size_lo = struct.unpack('<I', ext4_inode[4:8])[0]

        ### Analyse inode flags ###
        i_flags = struct.unpack('<I', ext4_inode[32:36])[0]
        # Extent flags.
        if ((i_flags & 0x80000) == 0x80000):
            EXT4_EXTENTS_FL = 1
        else:
            EXT4_EXTENTS_FL = 0
        # Inline data.
        if ((i_flags & 0x10000000) == 0x10000000):
            EXT4_INLINE_DATA_FL = 1
        else:
            EXT4_INLINE_DATA_FL = 0
        # Huge file.
        if ((i_flags & 0x40000) == 0x40000):
            EXT4_HUGE_FILE_FL = 1
        else:
            EXT4_HUGE_FILE_FL = 0

        i_blocks_lo = struct.unpack('<I', ext4_inode[28:32])[0]
        union_osd2 = ext4_inode[116:116+12]
        i_blocks_high = struct.unpack('<H', union_osd2[0:2])[0]
        # Get i_block.
        i_block = ext4_inode[40:100]
        # If the inode doesn't use extents, pass.
        if EXT4_EXTENTS_FL != 1:
            logging.debug('Extents not used.')
            ext4_file.close()
            return

        ### Analyse extent tree header ###
        # Check the magic number.
        eh_magic = struct.unpack('<H', i_block[0:2])[0]
        if eh_magic != 0xF30A:
            logging.error('Invalid magic number for extent.')
            ext4_file.close()
            return
        eh_entries = struct.unpack('<H', i_block[2:4])[0]
        if eh_entries <= 0:
            ext4_file.close()
            return
        eh_max = struct.unpack('<H', i_block[4:6])[0]
        eh_depth = struct.unpack('<H', i_block[6:8])[0]
        if eh_depth > 0:
            logging.debug(
                'depth greater than 0 not supported ('
                + str(eh_depth) + ')'
            )
            ei_block = struct.unpack('<I', i_block[12:16])[0]
            ei_leaf_lo = struct.unpack('<I', i_block[16:20])[0]
            ext4_file.close()
            return

        ### Analyse leaf nodes ###
        ee_block = struct.unpack('<I', i_block[12:16])[0]
        ee_len = struct.unpack('<H', i_block[16:18])[0]
        if ee_len > 32768:
            ee_len = ee_len - 32768
        ee_start_hi = struct.unpack('<H', i_block[18:20])[0]
        ee_start_lo = struct.unpack('<I', i_block[20:24])[0]
        logging.debug(
            'Leaf node data:\n\t '
            + 'First file block number that this extent covers '
            + str(ee_block) + '\n\t '
            + 'Number of blocks covered by extent '
            + str(ee_len) + '\n\t '
            + 'Upper 16-bits of the block number to which this extent points '
            + str(ee_start_hi) + '\n\t '
            + 'Lower 32-bits of the block number to which this extent points '
            + str(ee_start_lo)
        )

        # Compute the 48-bit block number and go to that point in file.
        total_48_bit_block_number = ee_start_hi << 32 | ee_start_lo
        ext4_file.seek(total_48_bit_block_number * self.block_size)

        # Compute the number of blocks and block size for reads.
        read_size = 512
        num_blocks_to_read = i_blocks_lo
        if self.RO_COMPAT_HUGE_FILE == 1:
            num_blocks_to_read = i_blocks_lo + (i_blocks_high << 32)
            if EXT4_HUGE_FILE_FL == 1:
                read_size = self.block_size
        ext4_apk_entry = ext4_file.read(num_blocks_to_read * read_size)

        # Write the bytes out to file.
        outfile = os.path.join(self.path_app_folder, apk_name)
        fo_apk_file = open(outfile, 'wb', 0)
        fo_apk_file.write(ext4_apk_entry)
        fo_apk_file.close()

        ext4_file.close()
