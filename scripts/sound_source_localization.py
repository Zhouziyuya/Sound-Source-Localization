# !/usr/bin/env python

"""In this script, run_sound_source will find the all potential candidates for
where the sound source is located."""


from itertools import combinations
from scripts.utils import ThreadWithReturnValue, convert_to_one_list, \
    check_list_of_lists_are_same_length

import numpy as np
import scipy.io as sio
import pyroomacoustics as pra


# TODO:
#  3) Test Edge Cases
#  4) Figure out how to use the GPU threads to run this

class SoundSourceLocation(object):
    """SoundSourceLocation finds the potential location points of a
       sound source using a distance of arrival (DOA) method via a
       combination of microphone pairings.

    Attributes:
        filepath: (string) filepath of where the data is located
        algo_name: (string) specific distance of arrival (DOA) method
        num_sources: (integer) number of sources to find. Default is 1
        recovered: (boolean) specifies whether to use recovered sound cycles.
                   Default is False

        transform: (boolean) DEBUG -- figure out whether to use the new version
                   or the deprecated version

        sound_speed: (float) specific speed of sound
        combinations_number: (integer) number of microphone to use
        fs: (integer) specific sampling frequency. Default is 16000
        fft_size: (integer) specific FFT size. Default is 256
        freq_range: (list) specific frequency range to isolate for.
                    Default range is 0 - 256
        tol: (float) specific tolerance to use for distance between
             each point in the radius
        radius: (numpy array) values for radius
        s1_bool: (boolean) indicates whether to find S1 or S2 sound source
    """

    def __init__(self, filepath, algo_name, num_sources=1, recovered=False,
                 transform=False):
        """Initializes SoundSourceLocation with filepath, algo_name, num_sources."""

        self.filepath = filepath
        self.algo_name = algo_name
        self.num_sources = num_sources
        self.recovered = recovered

        # TODO: DEBUG
        self.transform = transform

        # Constants
        self.sound_speed = 30
        self.combinations_number = 3
        self.fs = 16000
        self.fft_size = 256
        self.freq_range = [0, 250]
        self.tol = 1e-3  # 3e-3
        self.radius = np.arange(0, 0.5, self.tol)[:, np.newaxis]

        self.s1_bool = True

    @staticmethod
    def create_microphone_locations_list():
        """Returns microphone locations list."""

        # Microphone x,y,z locations
        x_locations = [-0.102235, -0.052197, -0.027304]
        y_locations = [-0.109982]
        z_locations = [0.056388, 0.001524, -0.053340, -0.108204]

        # Return the microphone list
        return [[x, y, z] for x in x_locations for y in y_locations for z in z_locations]

    @staticmethod
    def get_centroid(*args):
        """Returns the center of n number of microphones (centroid).

            Args:
                *args: (list) location of each n microphone

            Returns:
                (numpy array) the center of the microphones

            Raises:
                ValueError: Microphone location list is empty
                ValueError: Microphone location list contains None
                ValueError: Not all the microphones in list are the
                            same length
                TypeError: A microphone is not a float
        """
        if not convert_to_one_list(args):
            raise ValueError('Error. Microphone location list is empty.')

        if None in convert_to_one_list(args):
            raise ValueError('Error. Microphone location list contains None.')

        if not check_list_of_lists_are_same_length(args):
            raise ValueError('Error. Not all microphone locations have same length!')

        if not all([isinstance(mic_loc, float) for mic_loc in convert_to_one_list(args)]):
            raise TypeError('Error. Microphone location list '
                            'does not contain a float type.')

        microphone_array = np.array(*args)

        return np.sum(microphone_array, axis=0) / len(*args)

    def get_sound_data(self, name_of_source):
        """Returns the sound data depending on the specific sound source
           and cycle number related.

            Args:
                name_of_source: (string) specifies each sound cycle

            Returns:
                sound_data: (numpy array) matrix of all the sound data

            Raises:
                TypeError: Recovered is not a boolean type
                NameError: name_of_source is not in the dictionary of
                            source names
        """

        if not isinstance(self.recovered, bool):
            raise TypeError("recovered is supposed to be a boolean.\n {}"
                            " is not a boolean.".format(self.recovered))

        # Create a dictionary with all cycles:
        # Recovered S1 and S2 (top),
        # Regular S1 and S1 (bottom)
        if self.recovered:
            source_name_dict = {f'S{x}_Cycle{y}': [f'Recovered_S{x}/S{x}_Cycle{y}',
                                                   f'S{x}'] for x in range(1, 3) for y in range(24)}
        else:
            source_name_dict = {f'S{x}_Cycle{y}': [f'S{x}/S{x}_Cycle{y}', f'S{x}']
                                for x in range(1, 3) for y in range(24)}

        if name_of_source not in source_name_dict.keys():
            raise NameError("{} name not in cycle list".format(name_of_source))

        # Match the correct data with the name
        full_data_file_path = "".join([self.filepath,
                                       source_name_dict.get(name_of_source)[0]])
        data = sio.loadmat(full_data_file_path)

        return data.get(source_name_dict.get(name_of_source)[1])

    def get_mic_match_with_sound_data(self, data, *args):
        """Returns each of the n microphone locations and the signals list
           corresponding to the specific microphone. Note: The microphone
           locations are under a new coordinate system in relation to the center
           of the box (whose center = [(0.34925/2),(0.219964/2),(0.2413/2)]
           is the origin)

            Args:
                data: (numpy array) the signal associated with each microphone
                *args: (list) list of the microphones

            Returns:
                signal_list: (list) list of the associated signals
                microphone locations: (list) list of the microphone locations

            Raises:
                 ValueError: The signal list associated with
                             each microphone is empty
                 ValueError: The signal list associated with
                             each microphone contains None
                 ValueError: The signal list associated with
                             each microphone contains an empty string
                 ValueError: The microphone list is empty
        """

        if not data.tolist() or (data.size == 1 and None in data.tolist()):
            raise ValueError("Error. The signal is empty.")

        if None in data:
            raise ValueError('Error. The signal contains None.')

        if "" in data.tolist():
            raise ValueError('Error. The signal contains an empty string.')

        if not convert_to_one_list(args):
            raise ValueError('Error. Microphone list is empty.')

        signal_list, mic_location = [], []

        all_microphone_locations = self.create_microphone_locations_list()

        if len(all_microphone_locations) == len(data):
            all_microphone_locations_and_data = list(zip(all_microphone_locations,
                                                         (row for row in data)))

            # Dictionary of the microphone locations and their respective signals
            # The key is the specific microphone, and the value is a list--
            # the first is the microphone location, followed by the signal.
            # Note: order is mic number (from 1 -12), followed by
            # location of channel (to get actual signal)
            microphones_locations_and_signals_dict = {"".join(['mic', str(j+1)]): all_microphone_locations_and_data[j]
                                                      for j in range(len(all_microphone_locations_and_data))}

            # Look for the microphone location and the microphone signal
            # in the list in the dictionary
            for arg in args:
                if arg in microphones_locations_and_signals_dict.keys():
                    mic_location.append(microphones_locations_and_signals_dict.get(arg)[0])
                    signal_list.append(microphones_locations_and_signals_dict.get(arg)[1])

            return signal_list, mic_location

        else:
            return f"Error. Mismatch in length of microphone location list " \
                   f"and length of signal list."

    def difference_of_arrivals(self, signal_list, *mic_location):
        """Returns an azimuth and co-latitude for each pair of
           microphones combinations. Note: all angles are returned in radians

            Args:
                signal_list: (list) microphones signals
                *mic_location: (list) location of each microphone

            Returns:
                 doa.azimuth_recon: (float) Azimuth angle
                 doa.colatitude_recon: (float) Co-latitude angle

            Raises:
                ValueError: Signal list is empty
                ValueError: None in Signal list
                ValueError: Microphone list is empty
                ValueError: None in microphone list
        """
        print(type(signal_list))
        print(signal_list)
        if not signal_list:
            raise ValueError('Error. Signal list is empty.')

        if np.array(signal_list).shape[0] == 1 and None in signal_list:
            raise ValueError('Error. None in signal list.')

        # This works for lists of lists, but not for single list
        if any([True for signal in signal_list if None in signal]):
            raise ValueError('Error. None in signal list.')

        if not mic_location:
            raise ValueError('Error. Microphone location list is empty.')

        if None in mic_location:
            raise ValueError('Error. None in microphone location list is empty.')

        # Add n-microphone array in [x,y,z] order
        m = np.vstack(list(zip(*mic_location)))

        # TODO: Figure out this deprecation
        # Create an array of a short fourier transformed frequency signal
        if self.transform:
            x = np.array([pra.stft(signal, self.fft_size, self.fft_size // 2,
                                   transform=np.fft.rfft).T for signal in signal_list])
        else:
            x = np.array([pra.transform.stft.analysis(signal, self.fft_size,
                                                      self.fft_size // 2).T for signal in signal_list])

        # Construct the new DOA object
        doa = pra.doa.algorithms.get(self.algo_name)(L=m, fs=self.fs,
                                                     nfft=self.fft_size,
                                                     c=self.sound_speed,
                                                     num_src=self.num_sources,
                                                     max_four=4, dim=3,
                                                     azimuth=np.linspace(-180., 180., 360) * np.pi / 180,
                                                     colatitude=np.linspace(-90., 90., 180) * np.pi / 180)

        doa.locate_sources(x, freq_range=self.freq_range)

        return doa.azimuth_recon, doa.colatitude_recon

    def split_and_conquer(self, the_centroid, cartesian_arr):
        """Returns the cartesian array multiplied by the radius and recenter
           for each source when looking for multiple sources.

            Args:
                the_centroid: the specific centroid associated with each
                              microphone combination
                cartesian_arr: the cartesian array before the multiplication
                               of the radius

            Returns:
                (numpy array) cartesian coordinates for each source

            Raises:
                TypeError: Cartesian array is not a numpy array
            """

        if not isinstance(cartesian_arr, np.ndarray):
            raise TypeError("Error. Cartesian array is not a numpy array")

        # Split up the array into the separate parts based on how many sources there are
        array_split = np.vsplit(cartesian_arr.T, self.num_sources)

        # Multiply each respective part by the radius and recenter it with the centroid
        for i in range(self.num_sources):
            array_split[i] = self.radius * array_split[i] + np.array(the_centroid)[np.newaxis, :]

        return np.vstack(array_split)

    def get_estimates(self, sound_data, *mic_split):
        """Returns the numpy array of location estimates for each microphone
           combination pairing and associated sound data. First, the signal
           and microphone locations are acquired. Next the centroid is gathered.
           Finally, the azimuth and co-latitude angles are generated and converted
           to cartesian coordinates, which are then multiplied by the radius.

           Args:
               sound_data: (numpy array) the specific sound data for microphone
                           pairings split
               *mic_split: (list) the specific microphone pairings split

            Returns:
                (numpy array) Array of the estimates

            Raises:
                ValueError: Sound data is empty
                ValueError: None in sound data
        """
        # TODO: Error handle empty cases...
        # if not sound_data.tolist():
        #     raise ValueError('Error. Sound data list is empty.')
        #
        # if None in sound_data:
        #     raise ValueError('Error. None in sound data list.')

        if not mic_split:
            raise ValueError('Error. Mic split list is empty.')

        if None in mic_split:
            raise ValueError('Error. None in mic split list is empty.')

        signal, mic_locations = self.get_mic_match_with_sound_data(sound_data,
                                                                   *mic_split)
        centroid = self.get_centroid(mic_locations)
        azimuth_recon, colatitude_recon = self.difference_of_arrivals(signal,
                                                                      mic_locations)

        cartesian_coordinates = np.array([np.cos(azimuth_recon)*np.sin(colatitude_recon),
                                          np.sin(azimuth_recon)*np.sin(colatitude_recon),
                                          np.cos(colatitude_recon)])

        if self.num_sources > 1:
            return self.split_and_conquer(centroid, cartesian_coordinates)
        return self.radius * cartesian_coordinates.T + np.array(centroid)[np.newaxis, :]

    def process_potential_estimates(self, all_sound_data):
        """Returns all the estimates for all the microphone combinations
           and re-centers according to the room dimension specifications.
           Microphone combinations are split up into equal chunks and
           to be used in multiple threads to decrease time to find estimates.

           Args:
               all_sound_data: (numpy array) the entire microphone signal data

            Returns:
                numpy array of the potential estimates re-centered according
                to the room specifications.
        """

        if self.s1_bool:
            # List of specific microphones to quickly find S1
            # (where M and T are located)
            mics = ["".join(['mic', str(i)]) for i in [2, 3, 6, 7, 10, 11]]

        else:
            # List of specific microphones to quickly find S2
            # (where P and A are located)
            mics = ["".join(['mic', str(i)]) for i in [1, 2, 5, 6, 9, 10]]

        mic_list = list(combinations(mics, self.combinations_number))

        splits = len(mic_list) // 5

        # Split up the mic list into chunks of the same size
        mic_split_list = [mic_list[i * splits:(i+1) * splits]
                          for i in range((len(mic_list)+splits-1) // splits)]

        outputs_list = []

        # TODO: Test if Multithread is actually faster??
        # Go through all the chunks in the multi-thread
        for j in range(splits):
            thread1 = ThreadWithReturnValue(target=self.get_estimates,
                                            args=(all_sound_data,
                                                  *mic_split_list[0][j]))
            thread2 = ThreadWithReturnValue(target=self.get_estimates,
                                            args=(all_sound_data,
                                                  *mic_split_list[1][j]))
            thread3 = ThreadWithReturnValue(target=self.get_estimates,
                                            args=(all_sound_data,
                                                  *mic_split_list[2][j]))
            thread4 = ThreadWithReturnValue(target=self.get_estimates,
                                            args=(all_sound_data,
                                                  *mic_split_list[3][j]))
            thread5 = ThreadWithReturnValue(target=self.get_estimates,
                                            args=(all_sound_data,
                                                  *mic_split_list[4][j]))

            # Start the multi-thread
            thread1.start()
            thread2.start()
            thread3.start()
            thread4.start()
            thread5.start()

            estimate_1 = thread1.join()
            estimate_2 = thread2.join()
            estimate_3 = thread3.join()
            estimate_4 = thread4.join()
            estimate_5 = thread5.join()

            outputs_list.extend((estimate_1, estimate_2, estimate_3,
                                 estimate_4, estimate_5))

        all_estimates = np.array(outputs_list)

        # Reshape them to (_, 3) which is proper format
        potential_sources = np.reshape(all_estimates,
                                       (all_estimates.shape[0]*all_estimates.shape[1],
                                        all_estimates.shape[2]))

        # Re-center the points, add the x,y,z location of the center of the
        # room to the obtained point
        # Format: Width, Depth, Length
        # Dimensions of Room (cm): [35, 22, 24]
        room_dim = np.array([0.34925, 0.219964, 0.2413])
        center_of_room = room_dim / 2

        # Reconvert all the potential source points
        # Format: (Width, Depth, Length)
        return np.add(center_of_room, potential_sources)

    def generate_potential_sources(self):
        cycles = ["".join(['Cycle', str(i)]) for i in range(24)]
        sound_sources = ["".join(['S', str(i)]) for i in range(1, 3)]
        sound_list = ["_".join([sound_source, cycle])
                      for sound_source in sound_sources for cycle in cycles]

        for source_name in sound_list:
            if source_name in ["".join(["_".join(['S2', 'Cycle']),
                                        str(j)]) for j in range(24)]:
                self.s1_bool = False
            sound_data_of_interest = self.get_sound_data(source_name)
            yield source_name, self.process_potential_estimates(sound_data_of_interest)

    def run(self):
        """Runs all the functions."""

        cycles = ["".join(['Cycle', str(i)]) for i in range(24)]
        sound_sources = ["".join(['S', str(i)]) for i in range(1, 3)]
        # sound_list = ["_".join([sound_source, cycle]) for sound_source in sound_sources for cycle in cycles]

        # TODO:
        #  1) Do I want to output for each Source (S1, S2) and Cycle?
        # for source_name in sound_list:
        #     if source_name in ["".join(["_".join(['S2', 'Cycle']), str(j)]) for j in range(24)]:
        #         self.s1_bool = False
        #     self.process_potential_estimates(self.get_sound_data(source_name))

        # DEBUG:
        cycles_of_interest = cycles[:2]
        sound_source_of_interest = sound_sources[0]
        sound_source_cycle_of_interest = ["_".join([sound_source_of_interest, cycle])
                                          for cycle in cycles_of_interest]
        the_estimates = self.process_potential_estimates(self.get_sound_data(sound_source_cycle_of_interest[0]))
        return sound_source_cycle_of_interest, the_estimates

        # for source_name_of_interest in sound_source_cycle_of_interest:
        #     sound_data_of_interest = self.get_sound_data(source_name_of_interest)
        #     the_estimates = self.process_potential_estimates(sound_data_of_interest)
        #     print(the_estimates)
        #
